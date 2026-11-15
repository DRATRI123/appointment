"""Delivery adapters. Each provider takes an ``OutboundMessage`` and returns a ``DeliveryResult``.

Swapping vendors is configuration (``EMAIL_PROVIDER``, ``SMS_PROVIDER``, ``WHATSAPP_PROVIDER``); credentials
come only from the environment. Errors are classified so the dispatcher can retry transient failures
(timeouts, 429, 5xx) and stop on permanent ones (bad number, rejected template, auth failure).
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class OutboundMessage:
    channel: str
    to: str  # email address or E.164 mobile
    body: str
    subject: str | None = None
    html: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    provider_template_id: str | None = None  # DLT / MSG91 flow / WhatsApp template name
    template_params: list[str] = field(default_factory=list)  # ordered values for provider templates
    locale: str = "en"
    reference: str | None = None  # our notification id, for provider-side correlation
    button_params: list[str] = field(default_factory=list)  # WhatsApp template URL-button parameter (copy-code button)
    sensitive: bool = False  # carries a one-time code: never logged


@dataclass
class DeliveryResult:
    provider: str
    ok: bool
    message_id: str | None = None
    retryable: bool = False
    error: str | None = None
    response: dict[str, Any] | None = None


class Provider(Protocol):
    name: str
    channel: str

    def send(self, message: OutboundMessage) -> DeliveryResult: ...

    def configured(self) -> bool: ...


class ProviderConfig:
    """Settings for one provider instance, used when a clinic brings its own SMS / email / WhatsApp account.

    Only the clinic's values are used for anything account-related, so a clinic's sender is never combined with the
    platform's credentials. Non-secret tuning (ports, timeouts, API version) falls back to the platform defaults.
    """

    INHERITED = frozenset({"smtp_port", "smtp_security", "smtp_timeout_seconds", "whatsapp_cloud_api_version", "notification_http_timeout_seconds"})

    def __init__(self, values: dict[str, Any] | None = None):
        self._values = {k: v for k, v in (values or {}).items() if v not in (None, "")}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._values:
            return self._values[name]
        return getattr(get_settings(), name) if name in self.INHERITED else None


def _cfg(provider: Any) -> Any:
    return getattr(provider, "_config", None) or get_settings()


# ----------------------------------------------------------------- disabled
@dataclass
class DisabledProvider:
    """The platform has no account for this channel (production: clinics may still bring their own). Nothing is sent
    and nothing is written to the log; the message is recorded as failed with a clear reason."""

    channel: str
    name: str = "disabled"

    def configured(self) -> bool:
        return False

    def send(self, message: OutboundMessage) -> DeliveryResult:
        return DeliveryResult(self.name, False, error=f"No {self.channel} provider is set up (the platform's {self.channel.upper()}_PROVIDER is 'disabled').")


# ----------------------------------------------------------------- console
@dataclass
class ConsoleProvider:
    """Development/test provider: logs the message and keeps the last 200 in memory."""

    channel: str
    name: str = "console"
    outbox: list[OutboundMessage] = field(default_factory=list)
    fail_next: list[DeliveryResult] = field(default_factory=list)  # tests can queue failures

    def configured(self) -> bool:
        return True

    def send(self, message: OutboundMessage) -> DeliveryResult:
        if self.fail_next:
            return self.fail_next.pop(0)
        self.outbox.append(message)
        del self.outbox[:-200]
        if message.sensitive:  # one-time codes never reach the logs; tests read them from the in-memory outbox
            log.info("notification.console", channel=message.channel, to=message.to, body="[one-time code hidden]")
        else:
            log.info("notification.console", channel=message.channel, to=message.to, subject=message.subject, body=message.body[:500])
        return DeliveryResult(provider=self.name, ok=True, message_id=f"console-{len(self.outbox)}")


# -------------------------------------------------------------------- SMTP
class SMTPEmailProvider:
    name = "smtp"
    channel = "email"

    def __init__(self, config: ProviderConfig | None = None):
        self._config = config

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.smtp_host and s.smtp_from)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="SMTP_HOST and SMTP_FROM are not set.")
        msg = EmailMessage()
        msg["Subject"] = message.subject or ""
        msg["From"] = formataddr((s.smtp_from_name or message.from_name or "", s.smtp_from))
        msg["To"] = message.to
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        msg["Message-ID"] = make_msgid(domain=s.smtp_from.split("@")[-1])
        if message.reference:
            msg["X-Notification-Id"] = message.reference
        msg.set_content(message.body)
        if message.html:
            msg.add_alternative(message.html, subtype="html")
        try:
            if s.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
            with server:
                if s.smtp_security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if s.smtp_username:
                    server.login(s.smtp_username, s.smtp_password or "")
                refused = server.send_message(msg)
            if refused:
                return DeliveryResult(self.name, False, error=f"Recipient refused: {refused}", response={"refused": {k: list(v) for k, v in refused.items()}})
            return DeliveryResult(self.name, True, message_id=msg["Message-ID"])
        except smtplib.SMTPAuthenticationError as exc:
            return DeliveryResult(self.name, False, error=f"SMTP authentication failed ({exc.smtp_code}).")
        except smtplib.SMTPRecipientsRefused as exc:
            return DeliveryResult(self.name, False, error=f"Recipient refused: {list(exc.recipients)}")
        except smtplib.SMTPResponseException as exc:
            return DeliveryResult(self.name, False, retryable=400 <= exc.smtp_code < 500, error=f"SMTP {exc.smtp_code}: {exc.smtp_error!r}")
        except (OSError, smtplib.SMTPException) as exc:
            return DeliveryResult(self.name, False, retryable=True, error=f"SMTP connection error: {exc}")


# -------------------------------------------------------------- HTTP base
def _http_result(provider: str, resp: httpx.Response, message_id: str | None) -> DeliveryResult:
    try:
        data = resp.json()
    except ValueError:
        data = {"text": resp.text[:500]}
    if 200 <= resp.status_code < 300:
        return DeliveryResult(provider, True, message_id=message_id, response=data if isinstance(data, dict) else {"data": data})
    retryable = resp.status_code == 429 or resp.status_code >= 500
    return DeliveryResult(provider, False, retryable=retryable, error=f"HTTP {resp.status_code}: {str(data)[:300]}", response=data if isinstance(data, dict) else {"data": data})


class _HTTPProvider:
    name = "http"
    channel = "sms"

    def __init__(self, client: httpx.Client | None = None, config: ProviderConfig | None = None):
        self._client = client
        self._config = config

    def client(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=get_settings().notification_http_timeout_seconds)

    def _post(self, url: str, **kwargs) -> httpx.Response | DeliveryResult:
        try:
            if self._client is not None:
                return self._client.post(url, **kwargs)
            with self.client() as c:
                return c.post(url, **kwargs)
        except httpx.HTTPError as exc:
            return DeliveryResult(self.name, False, retryable=True, error=f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ Twilio
class TwilioProvider(_HTTPProvider):
    """Twilio Programmable Messaging for SMS (``channel='sms'``) or WhatsApp (``channel='whatsapp'``)."""

    def __init__(self, channel: str, client: httpx.Client | None = None, config: ProviderConfig | None = None):
        super().__init__(client, config)
        self.channel = channel
        self.name = "twilio"

    def _from(self) -> str | None:
        s = _cfg(self)
        return s.twilio_whatsapp_from if self.channel == "whatsapp" else s.twilio_sms_from

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.twilio_account_sid and s.twilio_auth_token and self._from())

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="Twilio credentials or sender are not set.")
        sender = self._from() or ""
        to = message.to
        data: dict[str, str] = {"To": f"whatsapp:{to}" if self.channel == "whatsapp" and not to.startswith("whatsapp:") else to}
        if sender.startswith("MG"):
            data["MessagingServiceSid"] = sender
        else:
            data["From"] = sender if self.channel != "whatsapp" or sender.startswith("whatsapp:") else f"whatsapp:{sender}"
        if self.channel == "whatsapp" and message.provider_template_id:
            import json

            data["ContentSid"] = message.provider_template_id
            data["ContentVariables"] = json.dumps({str(i + 1): v for i, v in enumerate(message.template_params)})
        else:
            data["Body"] = message.body
        url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
        resp = self._post(url, data=data, auth=(s.twilio_account_sid or "", s.twilio_auth_token or ""))
        if isinstance(resp, DeliveryResult):
            resp.provider = self.name
            return resp
        sid = None
        try:
            sid = resp.json().get("sid")
        except ValueError:
            pass
        result = _http_result(self.name, resp, sid)
        if not result.ok and resp.status_code == 400:
            result.retryable = False  # invalid number, unverified sender, template mismatch
        return result


# ------------------------------------------------------------------- MSG91
class MSG91SMSProvider(_HTTPProvider):
    """MSG91 Flow API (India). The template's ``provider_template_id`` is the MSG91 flow/template id (DLT approved);
    variables are sent as var1..varN in the order the template lists them."""

    name = "msg91"
    channel = "sms"

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.msg91_auth_key and s.msg91_sender_id)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="MSG91_AUTH_KEY and MSG91_SENDER_ID are not set.")
        if not message.provider_template_id:
            return DeliveryResult(self.name, False, error="MSG91 needs the DLT-approved flow id on the SMS template (provider template id).")
        recipient: dict[str, str] = {"mobiles": message.to.lstrip("+")}
        for i, v in enumerate(message.template_params, start=1):
            recipient[f"var{i}"] = v
        payload = {"template_id": message.provider_template_id, "sender": s.msg91_sender_id, "short_url": "0", "recipients": [recipient]}
        resp = self._post("https://control.msg91.com/api/v5/flow/", json=payload, headers={"authkey": s.msg91_auth_key or "", "accept": "application/json"})
        if isinstance(resp, DeliveryResult):
            resp.provider = self.name
            return resp
        result = _http_result(self.name, resp, None)
        if result.ok and isinstance(result.response, dict):
            if result.response.get("type") == "error":
                return DeliveryResult(self.name, False, error=str(result.response.get("message"))[:300], response=result.response)
            result.message_id = str(result.response.get("message") or "") or None
        return result


# ----------------------------------------------------- Meta WhatsApp Cloud
class MetaWhatsAppProvider(_HTTPProvider):
    """WhatsApp Cloud API. Business-initiated messages must use an approved template: set the template name as
    ``provider_template_id`` (optionally ``name:language``, default ``en``); body parameters follow the template's
    variable order. Without a template id a plain text message is sent, which WhatsApp only delivers inside the
    24-hour customer service window."""

    name = "meta"
    channel = "whatsapp"

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.whatsapp_cloud_token and s.whatsapp_cloud_phone_number_id)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="WHATSAPP_CLOUD_TOKEN and WHATSAPP_CLOUD_PHONE_NUMBER_ID are not set.")
        to = message.to.lstrip("+")
        if message.provider_template_id:
            name, _, lang = message.provider_template_id.partition(":")
            payload: dict[str, Any] = {"messaging_product": "whatsapp", "to": to, "type": "template", "template": {
                "name": name, "language": {"code": lang or "en"},
                "components": ([{"type": "body", "parameters": [{"type": "text", "text": v or "-"} for v in message.template_params]}] if message.template_params else [])
                + [{"type": "button", "sub_type": "url", "index": str(i), "parameters": [{"type": "text", "text": v}]} for i, v in enumerate(message.button_params)],
            }}
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"preview_url": True, "body": message.body[:4096]}}
        url = f"https://graph.facebook.com/{s.whatsapp_cloud_api_version}/{s.whatsapp_cloud_phone_number_id}/messages"
        resp = self._post(url, json=payload, headers={"Authorization": f"Bearer {s.whatsapp_cloud_token}"})
        if isinstance(resp, DeliveryResult):
            resp.provider = self.name
            return resp
        mid = None
        try:
            mid = (resp.json().get("messages") or [{}])[0].get("id")
        except (ValueError, AttributeError, IndexError):
            pass
        result = _http_result(self.name, resp, mid)
        if not result.ok and resp.status_code in (400, 401, 403):
            result.retryable = False
        return result


# ---------------------------------------------------------------- registry
_console: dict[str, ConsoleProvider] = {ch: ConsoleProvider(channel=ch) for ch in ("email", "sms", "whatsapp")}
_overrides: dict[str, Provider] = {}


def console_provider(channel: str) -> ConsoleProvider:
    return _console[channel]


def set_provider(channel: str, provider: Provider | None) -> None:
    """Tests and integrations can install a provider for a channel; ``None`` restores configuration."""
    if provider is None:
        _overrides.pop(channel, None)
    else:
        _overrides[channel] = provider


def get_provider(channel: str) -> Provider:
    if channel in _overrides:
        return _overrides[channel]
    s = get_settings()
    choice = {"email": s.email_provider, "sms": s.sms_provider, "whatsapp": s.whatsapp_provider}.get(channel, "console")
    if choice == "console":
        return _console[channel]
    if choice == "disabled":
        return DisabledProvider(channel)
    if channel == "email" and choice == "smtp":
        return SMTPEmailProvider()
    if channel in ("sms", "whatsapp") and choice == "twilio":
        return TwilioProvider(channel)
    if channel == "sms" and choice == "msg91":
        return MSG91SMSProvider()
    if channel == "whatsapp" and choice == "meta":
        return MetaWhatsAppProvider()
    raise RuntimeError(f"Unknown {channel} provider '{choice}'.")


def provider_status() -> list[dict[str, Any]]:
    out = []
    for ch in ("email", "sms", "whatsapp"):
        try:
            p = get_provider(ch)
            out.append({"channel": ch, "provider": p.name, "configured": p.configured(), "is_console": p.name == "console", "error": None})
        except RuntimeError as exc:
            out.append({"channel": ch, "provider": None, "configured": False, "is_console": False, "error": str(exc)})
    return out
