"""Notification events, their audience, variables and the platform default templates.

Organizations override any (event, channel) template; anything not overridden falls back to these.
Templates use ``{{variable}}`` placeholders only; no logic is evaluated (see ``render.py``).
SMS bodies in India must match a DLT-registered template, and WhatsApp business-initiated messages
must use a template approved by Meta: set ``provider_template_id`` on the organization's template.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CUSTOMER = "customer"
STAFF = "staff"
CHANNELS = ("email", "sms", "whatsapp", "in_app")

COMMON = ["customer_name", "organization_name", "organization_phone", "service_name", "professional_name", "branch_name", "branch_address",
          "appointment_date", "appointment_time", "appointment_reference", "manage_link"]


@dataclass(frozen=True)
class Template:
    subject: str | None
    body: str


@dataclass(frozen=True)
class Event:
    code: str
    label: str
    audience: str
    description: str
    variables: list[str]
    default_channels: tuple[str, ...]
    templates: dict[str, Template] = field(default_factory=dict)


def _t(subject: str | None, email: str, short: str, in_app: str | None = None) -> dict[str, Template]:
    return {"email": Template(subject, email), "sms": Template(None, short), "whatsapp": Template(None, short), "in_app": Template(subject, in_app or short)}


EVENTS: dict[str, Event] = {e.code: e for e in [
    Event("appointment.pending_payment", "Booking received, payment due", CUSTOMER,
          "Sent when an online booking needs an advance. Includes the amount and payment link.",
          [*COMMON, "amount_due", "payment_deadline", "payment_link"], ("email", "sms", "whatsapp"),
          _t("Complete your payment for {{service_name}} on {{appointment_date}}",
             "Hello {{customer_name}},\n\nWe have reserved {{service_name}} with {{professional_name}} on {{appointment_date}} at {{appointment_time}} ({{branch_name}}).\n\n"
             "Please pay {{amount_due}} by {{payment_deadline}} to confirm it:\n{{payment_link}}\n\nAfter paying, enter the UTR on the same page. The clinic confirms your booking once they see the payment in their bank.\n\n"
             "Reference: {{appointment_reference}}\n{{organization_name}}",
             "{{organization_name}}: pay {{amount_due}} by {{payment_deadline}} to confirm {{service_name}} on {{appointment_date}} {{appointment_time}}. {{payment_link}}")),
    Event("appointment.confirmed", "Appointment confirmed", CUSTOMER,
          "Sent when the appointment is confirmed (payment verified, no payment needed, or confirmed by staff).",
          [*COMMON, "amount_paid", "meeting_link"], ("email", "sms", "whatsapp"),
          _t("Confirmed: {{service_name}} on {{appointment_date}} at {{appointment_time}}",
             "Hello {{customer_name}},\n\nYour appointment is confirmed.\n\n{{service_name}} with {{professional_name}}\n{{appointment_date}} at {{appointment_time}}\n{{branch_name}}, {{branch_address}}\n\n"
             "Join online: {{meeting_link}}\nPaid so far: {{amount_paid}}\n\nView, reschedule or cancel: {{manage_link}}\n\nReference: {{appointment_reference}}\n{{organization_name}} {{organization_phone}}",
             "{{organization_name}}: confirmed {{service_name}} with {{professional_name}} on {{appointment_date}} {{appointment_time}}, {{branch_name}}. Ref {{appointment_reference}}. {{manage_link}}")),
    Event("appointment.meeting_link", "Online consultation link", CUSTOMER,
          "Sent when the video link for an online appointment is ready (Google Meet, Zoom or a link added by staff).",
          [*COMMON, "meeting_link"], ("email", "sms", "whatsapp"),
          _t("Your video link for {{service_name}} on {{appointment_date}}",
             "Hello {{customer_name}},\n\nYour online consultation with {{professional_name}} is on {{appointment_date}} at {{appointment_time}}.\n\n"
             "Join here a few minutes early:\n{{meeting_link}}\n\nUse a quiet place with a good connection. Need to change the time? {{manage_link}}\n\n{{organization_name}} {{organization_phone}}",
             "{{organization_name}}: join your online consultation on {{appointment_date}} {{appointment_time}}: {{meeting_link}}")),
    Event("appointment.reminder", "Appointment reminder", CUSTOMER,
          "Sent before confirmed appointments at the hours set in notification settings.",
          [*COMMON, "hours_before", "meeting_link"], ("email", "sms", "whatsapp"),
          _t("Reminder: {{service_name}} on {{appointment_date}} at {{appointment_time}}",
             "Hello {{customer_name}},\n\nThis is a reminder of your appointment:\n\n{{service_name}} with {{professional_name}}\n{{appointment_date}} at {{appointment_time}}\n{{branch_name}}, {{branch_address}}\n\n"
             "Join online: {{meeting_link}}\n\nNeed to change it? {{manage_link}}\n\n{{organization_name}} {{organization_phone}}",
             "Reminder from {{organization_name}}: {{service_name}} on {{appointment_date}} at {{appointment_time}}, {{branch_name}}. {{manage_link}}")),
    Event("appointment.rescheduled", "Appointment rescheduled", CUSTOMER, "Sent when the date, time or professional changes.",
          [*COMMON, "previous_date", "previous_time"], ("email", "sms", "whatsapp"),
          _t("Rescheduled: {{service_name}} is now on {{appointment_date}} at {{appointment_time}}",
             "Hello {{customer_name}},\n\nYour appointment has moved from {{previous_date}} {{previous_time}} to {{appointment_date}} at {{appointment_time}} with {{professional_name}} ({{branch_name}}).\n\n"
             "Details: {{manage_link}}\n\n{{organization_name}}",
             "{{organization_name}}: {{service_name}} moved to {{appointment_date}} {{appointment_time}} with {{professional_name}}. {{manage_link}}")),
    Event("appointment.cancelled", "Appointment cancelled", CUSTOMER, "Sent when an appointment is cancelled by the customer or the clinic.",
          [*COMMON, "reason", "refund_note"], ("email", "sms", "whatsapp"),
          _t("Cancelled: {{service_name}} on {{appointment_date}}",
             "Hello {{customer_name}},\n\nYour appointment for {{service_name}} on {{appointment_date}} at {{appointment_time}} has been cancelled.\n{{reason}}\n\n{{refund_note}}\n\n"
             "Book again any time from our booking page.\n\n{{organization_name}} {{organization_phone}}",
             "{{organization_name}}: your {{service_name}} on {{appointment_date}} {{appointment_time}} is cancelled. {{refund_note}}")),
    Event("appointment.expired", "Booking released (unpaid)", CUSTOMER, "Sent when an unpaid booking is released after the payment window.",
          [*COMMON], ("email", "sms"),
          _t("Your booking for {{service_name}} was released",
             "Hello {{customer_name}},\n\nWe did not receive payment details in time, so the slot on {{appointment_date}} at {{appointment_time}} was released.\n\n"
             "If you already paid, reply to this message or call {{organization_phone}} with your UTR and we will sort it out.\n\n{{organization_name}}",
             "{{organization_name}}: your unpaid booking for {{appointment_date}} {{appointment_time}} was released. Paid already? Call {{organization_phone}} with your UTR.")),
    Event("payment.submitted", "Payment details received", CUSTOMER, "Acknowledges the UTR the customer submitted. Makes clear it is not yet verified.",
          [*COMMON, "amount_due", "utr"], ("email",),
          _t("We received your payment details",
             "Hello {{customer_name}},\n\nThanks. We received UTR {{utr}} for {{amount_due}}. The clinic will check it against their bank account and confirm your booking once it is verified.\n\n"
             "Status: {{manage_link}}\n\n{{organization_name}}",
             "{{organization_name}}: received UTR {{utr}}. Your booking is confirmed once the clinic verifies the payment. {{manage_link}}")),
    Event("payment.rejected", "Payment not verified", CUSTOMER, "Sent when staff could not match the payment. Includes the reason and a link to submit again.",
          [*COMMON, "amount_due", "utr", "reason", "payment_link", "payment_deadline"], ("email", "sms", "whatsapp"),
          _t("Action needed: we could not verify your payment",
             "Hello {{customer_name}},\n\nWe could not verify the payment with UTR {{utr}}: {{reason}}\n\nPlease check the details and submit again by {{payment_deadline}}:\n{{payment_link}}\n\n{{organization_name}} {{organization_phone}}",
             "{{organization_name}}: payment UTR {{utr}} not verified ({{reason}}). Please resubmit by {{payment_deadline}}: {{payment_link}}")),
    Event("payment.verified", "Payment received", CUSTOMER, "Receipt for a verified payment on an already confirmed appointment (e.g. a balance).",
          [*COMMON, "amount_paid", "payment_reference"], ("email",),
          _t("Payment received: {{amount_paid}}",
             "Hello {{customer_name}},\n\nWe received {{amount_paid}} for {{service_name}} on {{appointment_date}}. Payment reference {{payment_reference}}.\n\n{{organization_name}}",
             "{{organization_name}}: received {{amount_paid}} (ref {{payment_reference}}). Thank you.")),
    Event("refund.processed", "Refund sent", CUSTOMER, "Sent after staff record a refund they transferred.",
          [*COMMON, "refund_amount", "refund_reference", "refund_method"], ("email", "sms"),
          _t("Refund of {{refund_amount}} sent",
             "Hello {{customer_name}},\n\n{{organization_name}} has sent you a refund of {{refund_amount}} by {{refund_method}}. Transfer reference: {{refund_reference}}.\n\n"
             "It can take a little while to appear in your account. Contact us at {{organization_phone}} if it has not arrived within 3 working days.\n\n{{organization_name}}",
             "{{organization_name}}: refund of {{refund_amount}} sent by {{refund_method}}, ref {{refund_reference}}.")),
    Event("staff.new_booking", "New booking (staff)", STAFF, "Tells staff about new bookings. Goes to members who can manage appointments.",
          [*COMMON, "customer_mobile", "status"], ("in_app", "email"),
          _t("New booking: {{customer_name}}, {{appointment_date}} {{appointment_time}}",
             "New booking {{appointment_reference}}\n\n{{customer_name}} ({{customer_mobile}})\n{{service_name}} with {{professional_name}}\n{{appointment_date}} at {{appointment_time}}, {{branch_name}}\nStatus: {{status}}",
             "New booking: {{customer_name}}, {{service_name}} {{appointment_date}} {{appointment_time}}")),
    Event("staff.payment_to_verify", "Payment to verify (staff)", STAFF, "Tells verifiers a customer submitted a UTR.",
          [*COMMON, "amount_due", "utr", "payment_reference"], ("in_app",),
          _t("Payment to verify: {{amount_due}} from {{customer_name}}",
             "{{customer_name}} submitted UTR {{utr}} for {{amount_due}} ({{payment_reference}}). Check your bank account before approving.",
             "Verify {{amount_due}} from {{customer_name}}, UTR {{utr}}")),
    Event("staff.appointment_cancelled", "Customer cancelled (staff)", STAFF, "Tells staff when a customer cancels online.",
          [*COMMON, "reason"], ("in_app",),
          _t("Cancelled by customer: {{customer_name}}, {{appointment_date}} {{appointment_time}}",
             "{{customer_name}} cancelled {{service_name}} on {{appointment_date}} at {{appointment_time}}. {{reason}}",
             "{{customer_name}} cancelled {{service_name}} on {{appointment_date}} {{appointment_time}}. {{reason}}")),
    Event("staff.refund_requested", "Refund to approve (staff)", STAFF, "Tells approvers about a new refund request.",
          [*COMMON, "refund_amount", "reason"], ("in_app",),
          _t("Refund to approve: {{refund_amount}} for {{customer_name}}",
             "A refund of {{refund_amount}} for {{customer_name}} was requested: {{reason}}",
             "Refund to approve: {{refund_amount}} for {{customer_name}}")),
]}

# Which members receive staff events (by permission).
STAFF_RECIPIENT_PERMISSION = {
    "staff.new_booking": "appointments:write",
    "staff.payment_to_verify": "payments:verify",
    "staff.appointment_cancelled": "appointments:write",
    "staff.refund_requested": "refunds:approve",
}

SAMPLE_VALUES = {
    "customer_name": "Asha Patel", "customer_mobile": "+919812345678", "organization_name": "Sunrise Ayurveda", "organization_phone": "+91 80 4000 1234",
    "service_name": "Panchakarma consultation", "professional_name": "Dr. Mehta", "branch_name": "Indiranagar", "branch_address": "12, 100 Feet Road, Bengaluru",
    "appointment_date": "Mon, 16 Nov 2026", "appointment_time": "10:30 am", "appointment_reference": "APT-SUNRISE-01JD8Q", "manage_link": "https://example.com/o/sunrise/appointments/APT-SUNRISE-01JD8Q",
    "amount_due": "₹500.00", "amount_paid": "₹500.00", "payment_deadline": "Mon, 16 Nov 2026, 9:45 am", "payment_link": "https://example.com/o/sunrise/appointments/APT-SUNRISE-01JD8Q",
    "utr": "412345678901", "reason": "No credit found for this UTR", "payment_reference": "PAY-SUNRISE-01JD8R", "refund_amount": "₹500.00",
    "refund_reference": "412399998888", "refund_method": "UPI", "refund_note": "A refund of ₹500.00 has been requested; you will be told when it is sent.",
    "previous_date": "Sun, 15 Nov 2026", "previous_time": "4:00 pm", "hours_before": "24", "meeting_link": "", "status": "pending payment",
}
