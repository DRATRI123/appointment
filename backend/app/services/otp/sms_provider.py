"""SMS codes. Indian operators require a DLT-registered template; MSG91 sends its flow id with var1 = code."""
from __future__ import annotations

from app.notifications.providers import DeliveryResult, OutboundMessage
from app.services.otp.channels import Sender


def send_otp(sender: Sender, *, destination: str, code: str, minutes: int, clinic: str) -> DeliveryResult:
    body = f"{code} is your verification code for {clinic}. Valid for {minutes} minutes. Do not share it with anyone."
    message = OutboundMessage(channel="sms", to=destination, body=body, provider_template_id=sender.options.get("template_id") or None,
                              template_params=[code, str(minutes)], sensitive=True)
    return sender.provider.send(message)
