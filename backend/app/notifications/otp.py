"""OTP delivery through the configured SMS / email adapters (``OTP_PROVIDER=notifications``).

Login codes go by SMS for mobile numbers and by email for addresses; password-reset and email-verification
tokens go by email as links. Sending is synchronous because the user is waiting for the code.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.notifications.providers import OutboundMessage, get_provider
from app.notifications.render import email_html
from app.security.otp import OTPMessage

log = get_logger(__name__)


class OTPDeliveryError(AppError):
    status_code = 503
    code = "otp_delivery_failed"


class NotificationOTPProvider:
    name = "notifications"

    def send(self, message: OTPMessage) -> str | None:
        s = get_settings()
        minutes = max(1, s.otp_expire_seconds // 60)
        app_name = s.app_name
        base = s.frontend_url.rstrip("/")
        if message.purpose == "password_reset":
            text = f"Reset your password: {base}/reset-password?token={message.code}\n\nThe link expires soon. If you did not ask for this, ignore this email."
            out = OutboundMessage(channel="email", to=message.identifier, subject="Reset your password", body=text)
        elif message.purpose == "verify_email":
            text = f"Confirm your email address: {base}/verify-email?token={message.code}"
            out = OutboundMessage(channel="email", to=message.identifier, subject="Confirm your email address", body=text)
        elif "@" in message.identifier:
            text = f"Your sign-in code is {message.code}. It expires in {minutes} minutes. Never share this code."
            out = OutboundMessage(channel="email", to=message.identifier, subject=f"{message.code} is your sign-in code", body=text)
        else:
            text = f"{message.code} is your {app_name} sign-in code. Valid for {minutes} minutes. Do not share it."
            out = OutboundMessage(channel="sms", to=message.identifier, body=text, provider_template_id=s.otp_sms_template_id or None,
                                  template_params=[message.code, str(minutes)])
        if out.channel == "email":
            out.html = email_html(out.body, organization_name=app_name, footer="You receive this because someone used this address to sign in.")
        result = get_provider(out.channel).send(out)
        if not result.ok:
            log.warning("otp.delivery_failed", channel=out.channel, provider=result.provider, error=result.error)
            raise OTPDeliveryError("We could not send the code right now. Please try again in a minute.")
        return result.message_id
