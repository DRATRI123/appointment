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

from app.core.logging import get_logger
from app.services.platform_config import runtime_settings as get_settings  # panel values win over .env

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


# -------------------------------------------------------------------- Brevo
class BrevoEmailProvider(_HTTPProvider):
    """Brevo transactional email: POST https://api.brevo.com/v3/smtp/email with the ``api-key`` header."""

    name = "brevo"
    channel = "email"

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.brevo_api_key and (s.email_from or s.smtp_from))

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="The Brevo API key and the sender email are not set.")
        payload: dict[str, Any] = {"sender": {"email": s.email_from or s.smtp_from, "name": message.from_name or s.smtp_from_name or "Appointments"},
                                   "to": [{"email": message.to}], "subject": message.subject or "(no subject)", "textContent": message.body}
        if message.html:
            payload["htmlContent"] = message.html
        if message.reply_to:
            payload["replyTo"] = {"email": message.reply_to}
        resp = self._post("https://api.brevo.com/v3/smtp/email", json=payload, headers={"api-key": s.brevo_api_key or "", "accept": "application/json"})
        if isinstance(resp, DeliveryResult):
            resp.provider = self.name
            return resp
        mid = None
        try:
            mid = resp.json().get("messageId")
        except (ValueError, AttributeError):
            pass
        result = _http_result(self.name, resp, mid)
        if not result.ok and resp.status_code in (400, 401, 403):
            result.retryable = False
        return result


# ----------------------------------------------------------- Amazon SES / SNS
def _aws_client(service: str, s: Any):
    import boto3
    from botocore.config import Config

    return boto3.client(service, region_name=s.aws_region, aws_access_key_id=s.aws_access_key_id, aws_secret_access_key=s.aws_secret_access_key,
                        config=Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 2, "mode": "standard"}))


def _aws_failure(provider: str, exc: Exception) -> DeliveryResult:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
    retryable = code in ("Throttling", "ThrottlingException", "TooManyRequestsException", "ServiceUnavailable", "InternalFailure") or \
        type(exc).__name__ in ("EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError")
    return DeliveryResult(provider, False, retryable=retryable, error=f"{code or type(exc).__name__}: {str(exc)[:250]}")


class SESEmailProvider:
    """Amazon SES (API v2, SendEmail). The sender must be a verified identity in that region."""

    name = "ses"
    channel = "email"

    def __init__(self, config: ProviderConfig | None = None, client: Any = None):
        self._config, self._client = config, client

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.aws_region and s.aws_access_key_id and s.aws_secret_access_key and (s.email_from or s.smtp_from))

    def send(self, message: OutboundMessage) -> DeliveryResult:
        from email.utils import formataddr as _fa

        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="The AWS region, access keys and a verified sender email are needed for Amazon SES.")
        body: dict[str, Any] = {"Text": {"Data": message.body, "Charset": "UTF-8"}}
        if message.html:
            body["Html"] = {"Data": message.html, "Charset": "UTF-8"}
        args: dict[str, Any] = {"FromEmailAddress": _fa((message.from_name or s.smtp_from_name or "Appointments", s.email_from or s.smtp_from)),
                                "Destination": {"ToAddresses": [message.to]},
                                "Content": {"Simple": {"Subject": {"Data": message.subject or "(no subject)", "Charset": "UTF-8"}, "Body": body}}}
        if message.reply_to:
            args["ReplyToEmailAddresses"] = [message.reply_to]
        try:
            resp = (self._client or _aws_client("sesv2", s)).send_email(**args)
        except Exception as exc:  # noqa: BLE001 - botocore errors
            return _aws_failure(self.name, exc)
        return DeliveryResult(self.name, True, message_id=resp.get("MessageId"))


class SNSSMSProvider:
    """Amazon SNS SMS (Publish to a phone number). For India, the DLT entity and template IDs are sent as the
    AWS.MM.SMS.EntityId / AWS.MM.SMS.TemplateId attributes."""

    name = "sns"
    channel = "sms"

    def __init__(self, config: ProviderConfig | None = None, client: Any = None):
        self._config, self._client = config, client

    def configured(self) -> bool:
        s = _cfg(self)
        return bool(s.aws_region and s.aws_access_key_id and s.aws_secret_access_key)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="The AWS region and access keys are needed for Amazon SNS.")
        attrs: dict[str, Any] = {"AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}}
        if s.sns_sender_id:
            attrs["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": s.sns_sender_id}
        if s.dlt_entity_id:
            attrs["AWS.MM.SMS.EntityId"] = {"DataType": "String", "StringValue": s.dlt_entity_id}
        if message.provider_template_id:
            attrs["AWS.MM.SMS.TemplateId"] = {"DataType": "String", "StringValue": message.provider_template_id}
        try:
            resp = (self._client or _aws_client("sns", s)).publish(PhoneNumber=message.to, Message=message.body, MessageAttributes=attrs)
        except Exception as exc:  # noqa: BLE001
            return _aws_failure(self.name, exc)
        return DeliveryResult(self.name, True, message_id=resp.get("MessageId"))


# ------------------------------------------------------------------ 2Factor
class TwoFactorSMSProvider(_HTTPProvider):
    """2Factor.in, for sign-in codes only: GET https://2factor.in/API/V1/{key}/SMS/{phone}/{code}/{template}.
    Other SMS (reminders, confirmations) are refused with a clear message so the fallback provider sends them;
    2Factor's transactional-SMS API is not used because its parameters could not be confirmed from official docs."""

    name = "twofactor"
    channel = "sms"

    def configured(self) -> bool:
        return bool(_cfg(self).twofactor_api_key)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        from urllib.parse import quote

        s = _cfg(self)
        if not self.configured():
            return DeliveryResult(self.name, False, error="The 2Factor API key is not set.")
        if not (message.sensitive and message.template_params):
            return DeliveryResult(self.name, False, error="2Factor is set up for sign-in codes only. Choose another SMS provider (or a fallback) for other messages.")
        code = message.template_params[0]
        phone = message.to.lstrip("+")
        url = f"https://2factor.in/API/V1/{quote(s.twofactor_api_key or '', safe='')}/SMS/{quote(phone, safe='')}/{quote(code, safe='')}"
        if message.provider_template_id:
            url += f"/{quote(message.provider_template_id, safe='')}"
        try:
            if self._client is not None:
                resp = self._client.get(url)
            else:
                with self.client() as c:
                    resp = c.get(url)
        except httpx.HTTPError as exc:
            return DeliveryResult(self.name, False, retryable=True, error=type(exc).__name__)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code == 200 and data.get("Status") == "Success":
            return DeliveryResult(self.name, True, message_id=str(data.get("Details") or "")[:120] or None)
        # The URL contains the API key: never put it into the stored error.
        return DeliveryResult(self.name, False, retryable=resp.status_code >= 500 or resp.status_code == 429,
                              error=f"HTTP {resp.status_code}: {str(data.get('Details') or '')[:200]}")


# -------------------------------------------------------------------- Gmail
class GmailProvider(_HTTPProvider):
    """Gmail API (users.messages.send) with a connected Google account (OAuth, scope gmail.send). The access token is
    passed in by whoever owns the connection (a clinic's Gmail integration)."""

    name = "gmail"
    channel = "email"

    def __init__(self, token_fn, sender: str, client: httpx.Client | None = None):
        super().__init__(client, None)
        self._token_fn, self._sender = token_fn, sender

    def configured(self) -> bool:
        return bool(self._sender)

    def send(self, message: OutboundMessage) -> DeliveryResult:
        import base64

        mail = EmailMessage()
        mail["From"] = formataddr((message.from_name or "", self._sender)) if message.from_name else self._sender
        mail["To"] = message.to
        mail["Subject"] = message.subject or "(no subject)"
        mail["Message-ID"] = make_msgid(domain=self._sender.split("@")[-1])
        if message.reply_to:
            mail["Reply-To"] = message.reply_to
        mail.set_content(message.body)
        if message.html:
            mail.add_alternative(message.html, subtype="html")
        raw = base64.urlsafe_b64encode(mail.as_bytes()).decode()
        try:
            token = self._token_fn()
        except Exception as exc:  # noqa: BLE001 - IntegrationAPIError (reconnect needed) or network
            return DeliveryResult(self.name, False, retryable=bool(getattr(exc, "retryable", False)), error=str(exc)[:300])
        resp = self._post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", json={"raw": raw},
                          headers={"Authorization": f"Bearer {token}"})
        if isinstance(resp, DeliveryResult):
            resp.provider = self.name
            return resp
        mid = None
        try:
            mid = resp.json().get("id")
        except (ValueError, AttributeError):
            pass
        result = _http_result(self.name, resp, mid)
        if not result.ok and resp.status_code in (400, 401, 403):
            result.retryable = False
        return result


# ----------------------------------------------------------------- fallback
class FallbackProvider:
    """Try the main provider; if it fails, try the fallback once. The result says which one sent it."""

    def __init__(self, primary: Any, secondary: Any):
        self.primary, self.secondary = primary, secondary
        self.name = primary.name
        self.channel = primary.channel

    def configured(self) -> bool:
        return self.primary.configured() or self.secondary.configured()

    def send(self, message: OutboundMessage) -> DeliveryResult:
        first = self.primary.send(message) if self.primary.configured() else DeliveryResult(self.primary.name, False, error="not set up")
        if first.ok or not self.secondary.configured():
            return first
        second = self.secondary.send(message)
        if second.ok:
            second.response = {**(second.response or {}), "fallback_after": f"{first.provider}: {first.error}"[:300]}
            return second
        second.error = f"{first.provider}: {first.error} | {second.provider}: {second.error}"[:500]
        second.retryable = first.retryable or second.retryable
        return second


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


def build_named(channel: str, choice: str) -> Provider:
    """The platform provider called ``choice`` for a channel, with the effective settings (panel over .env)."""
    if choice == "console":
        return _console[channel]
    if choice == "disabled":
        return DisabledProvider(channel)
    if channel == "email" and choice == "smtp":
        return SMTPEmailProvider()
    if channel == "email" and choice == "brevo":
        return BrevoEmailProvider()
    if channel == "email" and choice == "ses":
        return SESEmailProvider()
    if channel in ("sms", "whatsapp") and choice == "twilio":
        return TwilioProvider(channel)
    if channel == "sms" and choice == "msg91":
        return MSG91SMSProvider()
    if channel == "sms" and choice == "sns":
        return SNSSMSProvider()
    if channel == "sms" and choice == "twofactor":
        return TwoFactorSMSProvider()
    if channel == "whatsapp" and choice == "meta":
        return MetaWhatsAppProvider()
    raise RuntimeError(f"Unknown {channel} provider '{choice}'.")


def get_provider(channel: str) -> Provider:
    if channel in _overrides:
        return _overrides[channel]
    s = get_settings()
    choice = {"email": s.email_provider, "sms": s.sms_provider, "whatsapp": s.whatsapp_provider}.get(channel, "console")
    primary = build_named(channel, choice)
    fallback = {"email": s.email_fallback_provider, "sms": s.sms_fallback_provider}.get(channel)
    if fallback and fallback not in (choice, "console", "disabled") and choice not in ("console", "disabled"):
        return FallbackProvider(primary, build_named(channel, fallback))  # type: ignore[return-value]
    return primary


def provider_status() -> list[dict[str, Any]]:
    out = []
    for ch in ("email", "sms", "whatsapp"):
        try:
            p = get_provider(ch)
            out.append({"channel": ch, "provider": p.name, "configured": p.configured(), "is_console": p.name == "console", "error": None})
        except RuntimeError as exc:
            out.append({"channel": ch, "provider": None, "configured": False, "is_console": False, "error": str(exc)})
    return out
