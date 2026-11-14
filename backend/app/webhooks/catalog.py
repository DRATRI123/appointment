"""Webhook events and their payloads (API version ``2026-11``).

Payloads use public ids only and never include clinical notes, form answers, documents or payment screenshots.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

API_VERSION = "2026-11"

EVENTS: dict[str, str] = {
    "appointment.created": "A booking was made (online, by staff or through the API).",
    "appointment.confirmed": "An appointment was confirmed (payment verified, no payment needed, or confirmed by staff).",
    "appointment.rescheduled": "The date, time or professional changed.",
    "appointment.cancelled": "An appointment was cancelled by the customer or the clinic.",
    "appointment.expired": "An unpaid booking was released after the payment window.",
    "appointment.checked_in": "The customer arrived.",
    "appointment.completed": "The appointment was completed.",
    "appointment.no_show": "The customer did not come.",
    "payment.submitted": "A customer submitted a UTR for verification (not yet verified).",
    "payment.verified": "Staff verified a payment against the bank.",
    "payment.rejected": "Staff could not verify a payment.",
    "refund.processed": "Staff recorded a refund they sent.",
    "ping": "A test event sent from the developer portal.",
}

STATUS_EVENT = {"confirmed": "appointment.confirmed", "cancelled": "appointment.cancelled", "expired": "appointment.expired",
                "checked_in": "appointment.checked_in", "completed": "appointment.completed", "no_show": "appointment.no_show"}


def appointment_data(db: Session, appt) -> dict[str, Any]:
    from app.models import Branch, Customer, Professional, Service

    svc, pro, branch, cust = db.get(Service, appt.service_id), db.get(Professional, appt.professional_id), db.get(Branch, appt.branch_id), db.get(Customer, appt.customer_id)
    return {
        "id": appt.public_id, "reference": appt.reference, "status": appt.status, "start_at": appt.start_at.isoformat(), "end_at": appt.end_at.isoformat(),
        "timezone": appt.timezone, "consultation_mode": appt.consultation_mode, "source": appt.source, "meeting_link": appt.meeting_link,
        "service": {"id": svc.public_id, "name": svc.name} if svc else None,
        "professional": {"id": pro.public_id, "name": pro.display_name} if pro else None,
        "branch": {"id": branch.public_id, "name": branch.name} if branch else None,
        "customer": {"id": cust.public_id, "name": cust.full_name, "mobile": cust.mobile, "email": cust.email} if cust else None,
        "amounts": {"currency": appt.currency, "total_paise": appt.total_amount_paise, "advance_due_paise": appt.advance_due_paise, "paid_paise": appt.paid_amount_paise or 0},
    }


def payment_data(db: Session, payment) -> dict[str, Any]:
    from app.models import Appointment, PaymentSubmission
    from sqlalchemy import select

    appt = db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
    utr = db.scalar(select(PaymentSubmission.utr).where(PaymentSubmission.payment_id == payment.id, PaymentSubmission.is_superseded.is_(False)).order_by(PaymentSubmission.id.desc()))
    return {"id": payment.public_id, "reference": payment.reference, "status": payment.status, "method": payment.method, "kind": payment.kind,
            "amount_paise": payment.amount_paise, "verified_amount_paise": payment.verified_amount_paise, "utr": utr, "currency": payment.currency,
            "verified_at": payment.verified_at.isoformat() if payment.verified_at else None, "rejection_reason": payment.rejection_reason,
            "appointment": {"id": appt.public_id, "reference": appt.reference} if appt else None}


def refund_data(db: Session, refund) -> dict[str, Any]:
    from app.models import Payment

    p = db.get(Payment, refund.payment_id)
    return {"id": refund.public_id, "reference": refund.reference, "status": refund.status, "amount_paise": refund.amount_paise, "method": refund.refund_method,
            "refund_reference": refund.refund_reference, "processed_at": refund.processed_at.isoformat() if refund.processed_at else None,
            "payment": {"id": p.public_id, "reference": p.reference} if p else None}
