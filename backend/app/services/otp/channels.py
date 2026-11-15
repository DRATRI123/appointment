"""Which account delivers a channel's codes: the clinic's own (encrypted credentials) or the platform's.

Field definitions here drive the admin form and the API validation, so adding a provider is a single entry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.verification import MessagingProviderConfig
from app.notifications.providers import (
    MetaWhatsAppProvider,
    MSG91SMSProvider,
    Provider,
    ProviderConfig,
    SMTPEmailProvider,
    TwilioProvider,
    get_provider,
)
from app.security.crypto import decrypt_text

CHANNELS = ("sms", "email", "whatsapp")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    secret: bool = False
    required: bool = True
    maps_to: str | None = None  # ProviderConfig attribute the adapter reads
    help: str = ""


PROVIDERS: dict[str, dict[str, list[FieldSpec]]] = {
    "sms": {
        "msg91": [
            FieldSpec("sender_id", "Sender ID", maps_to="msg91_sender_id", help="6-letter DLT-registered header, e.g. AKSHAR"),
            FieldSpec("template_id", "DLT flow / template ID", help="MSG91 flow with variables var1 = code, var2 = minutes"),
            FieldSpec("auth_key", "Auth key", secret=True, maps_to="msg91_auth_key"),
        ],
        "twilio": [
            FieldSpec("account_sid", "Account SID", maps_to="twilio_account_sid"),
            FieldSpec("from_number", "From number or Messaging Service SID", maps_to="twilio_sms_from"),
            FieldSpec("auth_token", "Auth token", secret=True, maps_to="twilio_auth_token"),
        ],
    },
    "whatsapp": {
        "meta": [
            FieldSpec("phone_number_id", "Phone number ID", maps_to="whatsapp_cloud_phone_number_id", help="From WhatsApp Manager → API setup"),
            FieldSpec("template_name", "Approved authentication template name", help="Category “Authentication”, with the copy-code button"),
            FieldSpec("language", "Template language code", required=False, help="e.g. en, en_US, hi (default en)"),
            FieldSpec("access_token", "Permanent access token", secret=True, maps_to="whatsapp_cloud_token", help="System-user token with whatsapp_business_messaging"),
        ],
        "twilio": [
            FieldSpec("account_sid", "Account SID", maps_to="twilio_account_sid"),
            FieldSpec("from_number", "WhatsApp sender (whatsapp:+…)", maps_to="twilio_whatsapp_from"),
            FieldSpec("content_sid", "Approved content template SID (HX…)", help="Variable {{1}} = code"),
            FieldSpec("auth_token", "Auth token", secret=True, maps_to="twilio_auth_token"),
        ],
    },
    "email": {
        "smtp": [
            FieldSpec("host", "SMTP server", maps_to="smtp_host"),
            FieldSpec("port", "Port", required=False, maps_to="smtp_port", help="587 (STARTTLS) or 465 (SSL)"),
            FieldSpec("security", "Security", required=False, maps_to="smtp_security", help="starttls, ssl or none"),
            FieldSpec("username", "User name", required=False, maps_to="smtp_username"),
            FieldSpec("from_email", "Sender email", maps_to="smtp_from"),
            FieldSpec("from_name", "Sender name", required=False, maps_to="smtp_from_name"),
            FieldSpec("subject", "Email subject", required=False, help="May use {{code}}, {{clinic}}, {{minutes}}"),
            FieldSpec("template", "Email text", required=False, help="Must contain {{code}}. May use {{clinic}} and {{minutes}}"),
            FieldSpec("password", "Password", secret=True, required=False, maps_to="smtp_password"),
        ],
    },
}


@dataclass
class Sender:
    """A ready-to-use provider plus the template details the channel module needs."""

    provider: Provider
    source: str  # "clinic" | "platform"
    options: dict[str, Any]


def clinic_config(db: Session, organization_id: int, channel: str) -> MessagingProviderConfig | None:
    return db.scalar(select(MessagingProviderConfig).where(MessagingProviderConfig.organization_id == organization_id, MessagingProviderConfig.channel == channel))


def secrets_of(row: MessagingProviderConfig) -> dict[str, str]:
    return json.loads(decrypt_text(row.secrets_encrypted)) if row.secrets_encrypted else {}


def missing_fields(channel: str, provider: str, settings: dict[str, Any], secrets: dict[str, str]) -> list[str]:
    return [f.label for f in PROVIDERS[channel][provider] if f.required and not (secrets if f.secret else settings).get(f.key)]


def _build(channel: str, provider: str, values: dict[str, Any]) -> Provider:
    mapped = {f.maps_to: values.get(f.key) for f in PROVIDERS[channel][provider] if f.maps_to}
    if "smtp_port" in mapped and mapped["smtp_port"]:
        mapped["smtp_port"] = int(mapped["smtp_port"])
    config = ProviderConfig(mapped)
    if provider == "msg91":
        return MSG91SMSProvider(config=config)
    if provider == "twilio":
        return TwilioProvider(channel, config=config)
    if provider == "meta":
        return MetaWhatsAppProvider(config=config)
    if provider == "smtp":
        return SMTPEmailProvider(config=config)
    raise ValueError(f"Unknown provider {provider}")


def sender_for(db: Session, organization_id: int, channel: str) -> Sender | None:
    """The clinic's own enabled, complete account if it has one, else the platform's configured provider."""
    row = clinic_config(db, organization_id, channel)
    if row is not None and row.enabled:
        secrets = secrets_of(row)
        if missing_fields(channel, row.provider, row.settings, secrets):
            return None  # a half-configured clinic account must not silently fall back to the platform
        return Sender(_build(channel, row.provider, {**row.settings, **secrets}), "clinic", dict(row.settings))
    platform = get_provider(channel)
    if not platform.configured():
        return None
    s = get_settings()
    options = {"template_id": s.otp_sms_template_id} if channel == "sms" else {}
    if channel == "whatsapp" and s.otp_whatsapp_template:
        name, _, lang = s.otp_whatsapp_template.partition(":")
        options = {"template_name": name, "language": lang or "en", "content_sid": s.otp_whatsapp_template}
    if channel == "whatsapp" and platform.name != "console" and not s.otp_whatsapp_template:
        return None  # WhatsApp only delivers business-initiated codes through an approved template
    return Sender(platform, "platform", options)
