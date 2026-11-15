"""WhatsApp codes through the official WhatsApp Business Platform (Cloud API) or Twilio's WhatsApp sender.

Business-initiated messages need a template approved by Meta in the *Authentication* category; those templates carry
the code in the body and in the copy-code button. Personal WhatsApp accounts cannot send automated codes.
"""
from __future__ import annotations

from app.notifications.providers import DeliveryResult, OutboundMessage
from app.services.otp.channels import Sender


def send_otp(sender: Sender, *, destination: str, code: str, minutes: int, clinic: str) -> DeliveryResult:
    opts = sender.options
    if sender.provider.name == "twilio":
        template = opts.get("content_sid") or None
    else:
        template = f"{opts['template_name']}:{opts.get('language') or 'en'}" if opts.get("template_name") else None
    body = f"{code} is your verification code for {clinic}. For your security, do not share this code."
    message = OutboundMessage(channel="whatsapp", to=destination, body=body, provider_template_id=template, template_params=[code],
                              button_params=[code] if sender.provider.name == "meta" else [], sensitive=True)
    return sender.provider.send(message)
