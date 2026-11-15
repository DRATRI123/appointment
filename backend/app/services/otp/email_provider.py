"""Email codes, with the clinic's own subject and text if set (placeholders {{code}}, {{clinic}}, {{minutes}})."""
from __future__ import annotations

from app.notifications.providers import DeliveryResult, OutboundMessage
from app.notifications.render import email_html
from app.services.otp.channels import Sender

DEFAULT_SUBJECT = "{{code}} is your verification code for {{clinic}}"
DEFAULT_TEMPLATE = (
    "Your verification code for {{clinic}} is {{code}}.\n\n"
    "It expires in {{minutes}} minutes. If you did not try to book an appointment, you can ignore this email.\n\n"
    "Never share this code with anyone."
)


def render(text: str, *, code: str, clinic: str, minutes: int) -> str:
    return text.replace("{{code}}", code).replace("{{clinic}}", clinic).replace("{{minutes}}", str(minutes))


def send_otp(sender: Sender, *, destination: str, code: str, minutes: int, clinic: str) -> DeliveryResult:
    subject = render(sender.options.get("subject") or DEFAULT_SUBJECT, code=code, clinic=clinic, minutes=minutes)
    template = sender.options.get("template") or DEFAULT_TEMPLATE
    if "{{code}}" not in template:
        template = DEFAULT_TEMPLATE
    body = render(template, code=code, clinic=clinic, minutes=minutes)
    message = OutboundMessage(channel="email", to=destination, subject=subject[:200], body=body, from_name=sender.options.get("from_name") or clinic,
                              template_params=[code, str(minutes)], sensitive=True)
    message.html = email_html(body, organization_name=clinic, footer="You receive this because this address was entered on a booking page.")
    return sender.provider.send(message)
