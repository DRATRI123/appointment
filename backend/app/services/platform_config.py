"""Platform-wide integration settings that can come from ``.env`` **or** from the super admin panel.

Rule: a value saved in the panel wins; when the panel has no value, the ``.env`` value (or the built-in default) is
used. Every field shows where its current value comes from. "Use .env value" removes the panel value again.

Secrets (keys, passwords, tokens) are stored AES-256-GCM encrypted (``DATA_ENCRYPTION_KEY``) inside one
``system_settings`` row and are never sent back to the browser: only "set" and the last four characters.

What can never move to the panel: the database address, ``SECRET_KEY``, ``DATA_ENCRYPTION_KEY`` and
``BACKUP_ENCRYPTION_KEY``. The encryption key protects these very settings, so it cannot be stored inside them.

Processes (API, worker) re-read the row every few seconds, so a change made in the panel reaches every process without
a restart. A section is shown as Connected only after a real test with the values that are saved now.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config as _config
from app.core.exceptions import ValidationFailed
from app.core.time import utcnow

KEY = "platform.integrations"
REFRESH_SECONDS = 10


@dataclass(frozen=True)
class F:
    """One setting. ``name`` is the Settings attribute; the .env variable is ``name.upper()``."""

    name: str
    label: str
    kind: str = "text"  # text | secret | choice | number | bool
    choices: tuple[str, ...] = ()
    help: str = ""
    when: tuple[str, str] | None = None  # shown only when another field has this value, e.g. ("email_provider", "smtp")
    required: bool = False

    @property
    def secret(self) -> bool:
        return self.kind == "secret"

    @property
    def env_name(self) -> str:
        return self.name.upper()


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    description: str
    fields: tuple[F, ...]
    restart_needed: bool = False
    docs: str = ""


EMAIL_CHOICES = ("console", "smtp", "brevo", "ses", "disabled")
SMS_CHOICES = ("console", "msg91", "twilio", "twofactor", "sns", "disabled")
WHATSAPP_CHOICES = ("console", "meta", "twilio", "disabled")

SECTIONS: dict[str, Section] = {s.key: s for s in (
    Section("storage", "File storage", "Where uploaded files are kept: this server's disk or an S3-compatible bucket (AWS S3, "
            "Cloudflare R2, Backblaze B2, DigitalOcean Spaces, Wasabi, MinIO). Private files are encrypted before upload; "
            "the bucket stays private.", (
                F("s3_bucket", "Bucket name", required=True),
                F("s3_region", "Region", help="e.g. ap-south-1 (AWS Mumbai). Cloudflare R2: auto"),
                F("s3_endpoint_url", "Endpoint URL", help="Leave empty for AWS. R2: https://<account id>.r2.cloudflarestorage.com · "
                  "MinIO: http://minio:9000"),
                F("s3_prefix", "Folder inside the bucket", help="Optional, e.g. clinic-prod"),
                F("s3_access_key_id", "Access key ID", required=True),
                F("s3_secret_access_key", "Secret access key", "secret", required=True),
            ), docs="docs/integrations/s3-storage-integration.md"),
    Section("backup", "Off-site backup copy", "After each nightly encrypted backup, a copy is uploaded to this bucket. Uses the "
            "access keys from File storage.", (
                F("backup_s3_bucket", "Backup bucket", required=True, help="Can be the same bucket as files, or a separate one"),
                F("backup_s3_prefix", "Folder for backups", help="Default backups/"),
            ), docs="docs/backup-restore.md"),
    Section("google", "Google sign-in", "Only for the \"Sign in with Google\" button on the sign-in page. Clinics connect Calendar, Meet, "
            "Gmail, Contacts and Drive with their own Google Cloud app (Admin → Integrations → Google Cloud app).", (
                F("google_client_id", "OAuth client ID", required=True, help="Ends with .apps.googleusercontent.com"),
                F("google_client_secret", "OAuth client secret", "secret", help="Optional for sign-in; when set, Test checks the ID with Google"),
            ), docs="docs/integrations/google-integration.md"),
    Section("email", "Default email provider", "Used for clinics that have not connected their own email account.", (
                F("email_provider", "Provider", "choice", EMAIL_CHOICES, required=True),
                F("smtp_host", "SMTP server", when=("email_provider", "smtp"), required=True),
                F("smtp_port", "Port", "number", when=("email_provider", "smtp"), help="587 (STARTTLS) or 465 (SSL)"),
                F("smtp_security", "Security", "choice", ("starttls", "ssl", "none"), when=("email_provider", "smtp")),
                F("smtp_username", "User name", when=("email_provider", "smtp")),
                F("smtp_password", "Password", "secret", when=("email_provider", "smtp")),
                F("smtp_from", "Sender email", when=("email_provider", "smtp"), required=True),
                F("brevo_api_key", "Brevo API key", "secret", when=("email_provider", "brevo"), required=True),
                F("aws_region", "AWS region", when=("email_provider", "ses"), required=True, help="e.g. ap-south-1"),
                F("aws_access_key_id", "AWS access key ID", when=("email_provider", "ses"), required=True),
                F("aws_secret_access_key", "AWS secret access key", "secret", when=("email_provider", "ses"), required=True),
                F("email_from", "Sender email", help="For Brevo and Amazon SES: a verified sender address"),
                F("smtp_from_name", "Sender name", help="Default: the clinic's name"),
                F("email_fallback_provider", "Fallback provider", "choice", ("", *EMAIL_CHOICES[1:-1]),
                  help="Tried once when the main provider fails"),
            ), docs="docs/integrations/email-providers.md"),
    Section("sms", "Default SMS provider", "Used for clinics that have not connected their own SMS account. India needs DLT-"
            "approved sender IDs and templates.", (
                F("sms_provider", "Provider", "choice", SMS_CHOICES, required=True),
                F("msg91_auth_key", "MSG91 auth key", "secret", when=("sms_provider", "msg91"), required=True),
                F("msg91_sender_id", "MSG91 sender ID", when=("sms_provider", "msg91")),
                F("msg91_route", "MSG91 route", when=("sms_provider", "msg91"), help="4 = transactional"),
                F("twilio_account_sid", "Twilio account SID", when=("sms_provider", "twilio"), required=True),
                F("twilio_auth_token", "Twilio auth token", "secret", when=("sms_provider", "twilio"), required=True),
                F("twilio_sms_from", "Twilio from number", when=("sms_provider", "twilio"), required=True),
                F("twofactor_api_key", "2Factor API key", "secret", when=("sms_provider", "twofactor"), required=True),
                F("twofactor_sender_id", "2Factor sender ID", when=("sms_provider", "twofactor"), help="DLT header, 6 letters"),
                F("aws_region", "AWS region", when=("sms_provider", "sns"), required=True),
                F("aws_access_key_id", "AWS access key ID", when=("sms_provider", "sns"), required=True),
                F("aws_secret_access_key", "AWS secret access key", "secret", when=("sms_provider", "sns"), required=True),
                F("sns_sender_id", "Sender ID", when=("sms_provider", "sns"), help="DLT header (India)"),
                F("dlt_entity_id", "DLT principal entity ID", help="India: your registered entity ID"),
                F("otp_sms_template_id", "DLT template ID for sign-in codes"),
                F("sms_fallback_provider", "Fallback provider", "choice", ("", *SMS_CHOICES[1:-1])),
            ), docs="docs/integrations/sms-integration.md"),
    Section("whatsapp", "Default WhatsApp provider", "Official WhatsApp Business Platform only (Meta Cloud API or Twilio).", (
                F("whatsapp_provider", "Provider", "choice", WHATSAPP_CHOICES, required=True),
                F("whatsapp_business_account_id", "WhatsApp Business Account ID", when=("whatsapp_provider", "meta")),
                F("whatsapp_cloud_phone_number_id", "Phone number ID", when=("whatsapp_provider", "meta"), required=True),
                F("whatsapp_cloud_token", "Access token", "secret", when=("whatsapp_provider", "meta"), required=True),
                F("whatsapp_app_secret", "App secret (for delivery reports)", "secret", when=("whatsapp_provider", "meta")),
                F("whatsapp_webhook_verify_token", "Webhook verify token", "secret", when=("whatsapp_provider", "meta"),
                  help="Any long random text; enter the same in Meta's webhook settings"),
                F("whatsapp_cloud_api_version", "Graph API version", when=("whatsapp_provider", "meta")),
                F("twilio_whatsapp_from", "Twilio WhatsApp sender", when=("whatsapp_provider", "twilio"), required=True,
                  help="whatsapp:+…  (uses the Twilio SID and token from SMS)"),
                F("otp_whatsapp_template", "Approved sign-in code template", help="Meta: name:language · Twilio: content SID"),
            ), docs="docs/integrations/whatsapp-integration.md"),
    Section("monitoring", "Error tracking (Sentry)", "Server errors are reported to Sentry. Personal data is removed first.", (
                F("sentry_dsn", "Sentry DSN", "secret", required=True),
                F("sentry_traces_sample_rate", "Performance sampling (0–1)", "number"),
            ), restart_needed=True, docs="docs/integrations/analytics-integration.md"),
)}

FIELDS: dict[str, F] = {}
for _section in SECTIONS.values():
    for _f in _section.fields:
        FIELDS.setdefault(_f.name, _f)

# --------------------------------------------------------------------------------------------------- runtime cache
_lock = threading.Lock()
_state: dict[str, Any] = {"values": {}, "loaded_at": 0.0, "raw": None}


def _auto_refresh() -> bool:
    # Tests share one uncommitted session: a separate session would see nothing. They set values explicitly.
    return _config.get_settings().app_env != "test"


def _decode(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    values = dict(raw.get("values") or {})
    if raw.get("secrets"):
        from app.security.crypto import decrypt_text

        try:
            values.update(json.loads(decrypt_text(raw["secrets"])))
        except Exception:  # noqa: BLE001 - an unreadable row must not take the platform down; env values still apply
            from app.core.logging import get_logger

            get_logger(__name__).error("platform_config.decrypt_failed")
    return values


def _load(raw: dict[str, Any] | None) -> None:
    with _lock:
        _state["values"], _state["raw"], _state["loaded_at"] = _decode(raw), raw, time.monotonic()


def refresh_from(db: Session) -> None:
    """Load the panel values with this session (used right after a save and by tests)."""
    from app.models import SystemSetting

    _load(db.scalar(select(SystemSetting.value).where(SystemSetting.key == KEY)))


def reset_cache() -> None:
    _load(None)
    _state["loaded_at"] = 0.0


def overrides() -> dict[str, Any]:
    if _auto_refresh() and time.monotonic() - _state["loaded_at"] > REFRESH_SECONDS:
        try:
            # The read-only engine: on SQLite the write engine starts every transaction with BEGIN IMMEDIATE, which
            # would wait for a request that is already writing (and stall it). Reads never take the write lock.
            from app.core.database import ReadSessionLocal

            with ReadSessionLocal() as s:
                refresh_from(s)
        except Exception:  # noqa: BLE001 - database not ready yet (first start): .env values apply
            _state["loaded_at"] = time.monotonic()
    return _state["values"]


def value(name: str) -> Any:
    ov = overrides()
    if name in ov:
        return ov[name]
    return getattr(_config.get_settings(), name, None)


def source(name: str) -> str:
    if name in overrides():
        return "panel"
    return "env" if name in _config.get_settings().model_fields_set else "default"


class RuntimeSettings:
    """``_config.get_settings()`` with the panel values on top. Read-only."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in FIELDS:
            return value(name)
        return getattr(_config.get_settings(), name)


_runtime = RuntimeSettings()


def runtime_settings() -> Any:
    return _runtime


def fingerprint(names: list[str] | tuple[str, ...]) -> str:
    data = json.dumps({n: value(n) for n in names}, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------------------------------- admin service
@dataclass
class _Row:
    values: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    hints: dict[str, str] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)


def _hint(v: str) -> str:
    return f"…{v[-4:]}" if len(v) > 8 else "set"


def read_row(db: Session) -> _Row:
    from app.models import SystemSetting

    raw = db.scalar(select(SystemSetting.value).where(SystemSetting.key == KEY)) or {}
    secrets = {}
    if raw.get("secrets"):
        from app.security.crypto import decrypt_text

        secrets = json.loads(decrypt_text(raw["secrets"]))
    return _Row(dict(raw.get("values") or {}), secrets, dict(raw.get("hints") or {}), dict(raw.get("tests") or {}), dict(raw.get("storage") or {}))


def write_row(db: Session, row: _Row) -> None:
    from app.models import SystemSetting
    from app.security.crypto import encrypt_text

    raw = {"values": row.values, "secrets": encrypt_text(json.dumps(row.secrets)) if row.secrets else None, "hints": row.hints,
           "tests": row.tests, "storage": row.storage, "updated_at": utcnow().isoformat()}
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == KEY))
    if setting is None:
        db.add(SystemSetting(key=KEY, value=raw, description="Integration settings saved in the super admin panel (secrets encrypted)"))
    else:
        setting.value = raw
    db.flush()
    _load(raw)


def _coerce(f: F, raw: Any) -> Any:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    if f.kind == "number":
        try:
            num = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(f"{f.label} must be a number.", code="invalid_setting") from exc
        if f.name == "sentry_traces_sample_rate":
            if not 0 <= num <= 1:
                raise ValidationFailed("Performance sampling must be between 0 and 1.", code="invalid_setting")
            return num
        if not num.is_integer() or not 1 <= num <= 65535:
            raise ValidationFailed(f"{f.label} must be a whole number such as 587.", code="invalid_setting")
        return int(num)
    if f.kind == "bool":
        return bool(raw)
    text = str(raw).strip()
    if len(text) > 2000 or any(ord(c) < 32 for c in text):
        raise ValidationFailed(f"{f.label} is too long or contains invalid characters.", code="invalid_setting")
    if f.kind == "choice" and text not in f.choices:
        raise ValidationFailed(f"{f.label}: choose one of {', '.join(c for c in f.choices if c)}.", code="invalid_setting")
    return text


def check_environment_rules(effective: dict[str, Any]) -> None:
    """The panel follows the same safety rules as .env (app/core/config.py)."""
    s = _config.get_settings()
    chosen = {"email_provider": effective.get("email_provider"), "sms_provider": effective.get("sms_provider"),
              "whatsapp_provider": effective.get("whatsapp_provider")}
    real = [k for k, v in chosen.items() if v not in (None, "console", "disabled")]
    if s.app_env == "test" and real:
        raise ValidationFailed("Real message providers cannot be chosen in the test environment.", code="unsafe_setting")
    if s.app_env == "development" and real and not s.dev_allow_real_messages:
        raise ValidationFailed("This is a development computer: real messages are blocked. Set DEV_ALLOW_REAL_MESSAGES=true in .env "
                               "if you really want to send them from here.", code="unsafe_setting")
    if s.app_env in ("staging", "production") and "console" in chosen.values():
        raise ValidationFailed("On a server, 'console' would only write messages to the log. Choose a real provider or 'disabled'.",
                               code="unsafe_setting")


def section_state(db: Session, key: str, row: _Row | None = None) -> dict[str, Any]:
    section = SECTIONS[key]
    row = row or read_row(db)
    fields = []
    for f in section.fields:
        src = "panel" if (f.name in row.values or f.name in row.secrets) else ("env" if f.name in _config.get_settings().model_fields_set else "default")
        current = value(f.name)
        item = {"name": f.name, "env_name": f.env_name, "label": f.label, "kind": f.kind, "choices": list(f.choices), "help": f.help,
                "when": list(f.when) if f.when else None, "required": f.required, "source": src, "is_set": current not in (None, "")}
        if f.secret:
            item["hint"] = row.hints.get(f.name) if src == "panel" else (_hint(str(current)) if current else None)
        else:
            item["value"] = current
        fields.append(item)
    names = [f.name for f in section.fields]
    missing = [f.label for f in section.fields if f.required and _visible(f) and value(f.name) in (None, "")]
    test = row.tests.get(key) or {}
    fp = fingerprint(names)
    if missing:
        status = "not_configured"
    elif test and test.get("fingerprint") == fp:
        status = "connected" if test.get("ok") else "error"
    else:
        status = "untested"
    return {"key": key, "title": section.title, "description": section.description, "fields": fields, "status": status,
            "missing": missing, "last_test": test or None, "restart_needed": section.restart_needed, "docs": section.docs}


def _visible(f: F) -> bool:
    if not f.when:
        return True
    return value(f.when[0]) == f.when[1]


def save_section(db: Session, key: str, values: dict[str, Any], secrets: dict[str, str], clear: list[str]) -> _Row:
    section = SECTIONS.get(key)
    if section is None:
        raise ValidationFailed("Unknown settings section.", code="invalid_section")
    allowed = {f.name: f for f in section.fields}
    row = read_row(db)
    for name in clear:
        if name not in allowed:
            raise ValidationFailed(f"Unknown setting {name}.", code="invalid_setting")
        row.values.pop(name, None)
        row.secrets.pop(name, None)
        row.hints.pop(name, None)
    for name, raw in values.items():
        f = allowed.get(name)
        if f is None or f.secret:
            raise ValidationFailed(f"Unknown setting {name}.", code="invalid_setting")
        coerced = _coerce(f, raw)
        if coerced is None:
            row.values.pop(name, None)
        else:
            row.values[name] = coerced
    for name, raw in secrets.items():
        f = allowed.get(name)
        if f is None or not f.secret:
            raise ValidationFailed(f"Unknown secret {name}.", code="invalid_setting")
        text = (raw or "").strip()
        if not text:
            continue  # empty keeps the stored secret
        if len(text) > 4000 or any(ord(c) < 32 for c in text):
            raise ValidationFailed(f"{f.label} is too long or contains invalid characters.", code="invalid_setting")
        row.secrets[name], row.hints[name] = text, _hint(text)
    effective = {n: row.values.get(n, row.secrets.get(n, getattr(_config.get_settings(), n, None))) for n in FIELDS}
    check_environment_rules(effective)
    write_row(db, row)
    return row


def record_test(db: Session, key: str, ok: bool, message: str) -> dict[str, Any]:
    row = read_row(db)
    names = [f.name for f in SECTIONS[key].fields]
    result = {"ok": ok, "message": message[:400], "at": utcnow().isoformat(), "fingerprint": fingerprint(names)}
    row.tests[key] = result
    write_row(db, row)
    return result


def env_lines(db: Session, include_secrets: bool) -> str:
    """The panel values as .env lines, to copy into the server's .env file if you prefer to keep them there."""
    row = read_row(db)
    out = ["# Integration settings exported from the super admin panel on " + utcnow().strftime("%Y-%m-%d %H:%M UTC"),
           "# Values in the panel win over .env. After copying these into .env you can press \"Use .env value\" in the panel.", ""]
    for section in SECTIONS.values():
        lines = []
        for f in section.fields:
            if f.name in row.values:
                lines.append(f"{f.env_name}={row.values[f.name]}")
            elif f.name in row.secrets:
                lines.append(f"{f.env_name}={row.secrets[f.name] if include_secrets else '<hidden: export with secrets to include>'}")
        if lines:
            out.extend([f"# {section.title}", *dict.fromkeys(lines), ""])
    return "\n".join(out) + "\n"


def write_env_file(db: Session, path=None) -> dict[str, Any]:
    """Development computers only (START-APP.bat): write the panel values into backend/.env, so the same settings also
    work from .env. A copy of the old file is kept as .env.before-integrations. Servers manage .env with deploy.sh:
    there, download the lines instead."""
    import os
    import re
    from pathlib import Path

    from app.core.config import BASE_DIR

    if _config.get_settings().app_env != "development":
        raise ValidationFailed("Writing .env from the panel is only for a development computer. On a server, download the lines "
                               "and add them to the .env file that deploy.sh manages.", code="env_write_not_allowed")
    target = Path(path) if path else BASE_DIR / ".env"
    row = read_row(db)
    wanted: dict[str, str] = {}
    for section in SECTIONS.values():
        for f in section.fields:
            if f.name in row.values:
                wanted[f.env_name] = str(row.values[f.name])
            elif f.name in row.secrets:
                wanted[f.env_name] = row.secrets[f.name]
    for name in ("storage_backend",):
        if name in row.values:
            wanted[name.upper()] = str(row.values[name])
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if target.exists():
        target.with_name(".env.before-integrations").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out, done = [], set()
    for line in lines:
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in wanted:
            if m.group(1) not in done:
                out.append(f"{m.group(1)}={wanted[m.group(1)]}")
                done.add(m.group(1))
            continue
        out.append(line)
    missing = [k for k in wanted if k not in done]
    if missing:
        out.extend(["", "# Added from Super admin -> Integrations", *[f"{k}={wanted[k]}" for k in missing]])
    tmp = target.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return {"path": str(target), "written": sorted(wanted), "backup": str(target.with_name(".env.before-integrations"))}
