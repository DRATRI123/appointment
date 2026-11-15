"""Admin management of a clinic's own SMS / email / WhatsApp accounts.

Secrets are encrypted with DATA_ENCRYPTION_KEY (AES-256-GCM) and never sent back: the API returns only which secrets
are set and their last four characters. Leaving a secret empty on save keeps the stored one.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import Organization, User
from app.models.verification import MessagingProviderConfig
from app.notifications.providers import get_provider
from app.security.crypto import encrypt_text
from app.services.audit_service import RequestMeta, record_audit
from app.services.otp.channels import CHANNELS, PROVIDERS, clinic_config, missing_fields, secrets_of, sender_for
from app.services.otp.otp_generator import generate_code
from app.services.otp.otp_service import SENDERS, available_channels, load_policy, normalize_destination

_SAFE = re.compile(r"^[\x20-\x7e -￿\n\t]*$")


def _hint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 6 else "set"


class ProviderSettingsService:
    def __init__(self, db: Session, org: Organization, user: User | None, meta: RequestMeta | None = None):
        self.db, self.org, self.user, self.meta = db, org, user, meta

    def overview(self) -> dict[str, Any]:
        policy = load_policy(self.db, self.org)
        usable = set(available_channels(self.db, self.org, {**policy, "channels": list(CHANNELS)}))
        channels = []
        for ch in CHANNELS:
            row = clinic_config(self.db, self.org.id, ch)
            try:
                platform = get_provider(ch)
                platform_info = {"provider": platform.name, "configured": platform.configured()}
            except RuntimeError:
                platform_info = {"provider": None, "configured": False}
            own = None
            if row is not None:
                secrets = secrets_of(row)
                own = {
                    "provider": row.provider, "enabled": row.enabled, "settings": row.settings, "secrets_set": sorted(secrets),
                    "secret_hints": row.secret_hints or {}, "missing": missing_fields(ch, row.provider, row.settings, secrets),
                    "last_test_at": row.last_test_at, "last_test_ok": row.last_test_ok, "last_test_error": row.last_test_error,
                }
            sender = sender_for(self.db, self.org.id, ch)
            channels.append({"channel": ch, "own": own, "platform": platform_info, "usable": ch in usable,
                             "using": sender.source if sender else None, "enabled_in_policy": ch in policy.get("channels", [])})
        fields = {ch: {p: [{"key": f.key, "label": f.label, "secret": f.secret, "required": f.required, "help": f.help} for f in specs]
                       for p, specs in provs.items()} for ch, provs in PROVIDERS.items()}
        return {"policy": policy, "channels": channels, "providers": fields}

    def save(self, channel: str, *, provider: str, enabled: bool, settings: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
        if channel not in CHANNELS or provider not in PROVIDERS[channel]:
            raise ValidationFailed("Unknown provider for this channel.", code="invalid_provider")
        specs = {f.key: f for f in PROVIDERS[channel][provider]}
        clean: dict[str, Any] = {}
        for key, value in settings.items():
            spec = specs.get(key)
            if spec is None or spec.secret:
                raise ValidationFailed(f"Unknown setting “{key}”.", code="invalid_provider_setting")
            value = str(value).strip() if value is not None else ""
            if len(value) > (4000 if key == "template" else 300) or not _SAFE.match(value):
                raise ValidationFailed(f"{spec.label} is too long or contains invalid characters.", code="invalid_provider_setting")
            if value:
                clean[key] = value
        self._check_values(channel, provider, clean)
        row = clinic_config(self.db, self.org.id, channel)
        stored = secrets_of(row) if row is not None and row.provider == provider else {}
        for key, value in secrets.items():
            spec = specs.get(key)
            if spec is None or not spec.secret:
                raise ValidationFailed(f"Unknown secret “{key}”.", code="invalid_provider_setting")
            value = (value or "").strip()
            if value:  # empty keeps what is stored
                if len(value) > 500:
                    raise ValidationFailed(f"{spec.label} is too long.", code="invalid_provider_setting")
                stored[key] = value
        if enabled and (missing := missing_fields(channel, provider, clean, stored)):
            raise ValidationFailed("Fill in: " + ", ".join(missing) + ".", code="provider_incomplete")
        if row is None:
            row = MessagingProviderConfig(organization_id=self.org.id, channel=channel, provider=provider, settings={})
            self.db.add(row)
        before = {"provider": row.provider, "enabled": row.enabled, "settings": row.settings} if row.id else None
        row.provider, row.enabled, row.settings = provider, enabled, clean
        row.secrets_encrypted = encrypt_text(json.dumps(stored)) if stored else None
        row.secret_hints = {k: _hint(v) for k, v in stored.items()}
        row.updated_by_id = self.user.id if self.user else None
        row.last_test_at = row.last_test_ok = row.last_test_error = None  # credentials changed: test again
        self.db.flush()
        # Audit without secret values: only which secrets are set.
        record_audit(self.db, action="verification.provider_saved", actor=self.user, organization_id=self.org.id, entity_type="messaging_provider",
                     entity_id=channel, before=before, after={"provider": provider, "enabled": enabled, "settings": clean, "secrets_set": sorted(stored)}, meta=self.meta)
        return self.overview()

    def _check_values(self, channel: str, provider: str, values: dict[str, Any]) -> None:
        if provider == "smtp":
            if values.get("port") and not (values["port"].isdigit() and 1 <= int(values["port"]) <= 65535):
                raise ValidationFailed("Port must be a number such as 587.", code="invalid_provider_setting")
            if values.get("security") and values["security"] not in ("starttls", "ssl", "none"):
                raise ValidationFailed("Security must be starttls, ssl or none.", code="invalid_provider_setting")
            if values.get("from_email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", values["from_email"]):
                raise ValidationFailed("Enter a valid sender email.", code="invalid_provider_setting")
            if values.get("template") and "{{code}}" not in values["template"]:
                raise ValidationFailed("The email text must contain {{code}}.", code="invalid_provider_setting")
            if values.get("host") and not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", values["host"]):
                raise ValidationFailed("Enter the SMTP server name, e.g. smtp.gmail.com.", code="invalid_provider_setting")
        if provider == "msg91" and values.get("sender_id") and not re.fullmatch(r"[A-Za-z0-9]{3,11}", values["sender_id"]):
            raise ValidationFailed("Sender ID is the 3–11 letter header registered for DLT.", code="invalid_provider_setting")
        if provider == "meta" and values.get("phone_number_id") and not values["phone_number_id"].isdigit():
            raise ValidationFailed("The phone number ID is a number from WhatsApp Manager.", code="invalid_provider_setting")
        if provider == "twilio" and values.get("account_sid") and not re.fullmatch(r"AC[0-9a-fA-F]{32}", values["account_sid"]):
            raise ValidationFailed("A Twilio Account SID starts with AC followed by 32 characters.", code="invalid_provider_setting")

    def remove(self, channel: str) -> dict[str, Any]:
        row = clinic_config(self.db, self.org.id, channel)
        if row is None:
            raise NotFoundError("No account is set up for this channel.", code="provider_not_found")
        self.db.delete(row)
        record_audit(self.db, action="verification.provider_removed", actor=self.user, organization_id=self.org.id, entity_type="messaging_provider",
                     entity_id=channel, meta=self.meta)
        self.db.flush()
        return self.overview()

    def test(self, channel: str, destination: str) -> dict[str, Any]:
        """Send a real sample code through the channel's account to a number or address the admin enters."""
        if channel not in CHANNELS:
            raise ValidationFailed("Unknown channel.", code="invalid_channel")
        target = normalize_destination(channel, destination)
        sender = sender_for(self.db, self.org.id, channel)
        if sender is None:
            raise ValidationFailed("This channel has no complete account yet.", code="provider_incomplete")
        policy = load_policy(self.db, self.org)
        sample = generate_code(policy["code_length"])
        try:
            result = SENDERS[channel](sender, destination=target, code=sample, minutes=max(1, policy["expiry_seconds"] // 60), clinic=self.org.name)
            ok, error = result.ok, (result.error or "").replace(sample, "••••")[:300] or None
        except Exception as exc:
            ok, error = False, f"{type(exc).__name__}"
        row = clinic_config(self.db, self.org.id, channel) if sender.source == "clinic" else None
        if row is not None:
            row.last_test_at, row.last_test_ok, row.last_test_error = utcnow(), ok, None if ok else error
        record_audit(self.db, action="verification.provider_tested", actor=self.user, organization_id=self.org.id, entity_type="messaging_provider",
                     entity_id=channel, after={"ok": ok, "source": sender.source, "provider": sender.provider.name, "error": error}, meta=self.meta)
        self.db.flush()
        return {"ok": ok, "provider": sender.provider.name, "source": sender.source, "error": None if ok else error}
