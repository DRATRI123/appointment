"""Turn domain changes into webhook events (queued in the outbox, delivered by the worker)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.webhooks.catalog import STATUS_EVENT, appointment_data, payment_data, refund_data


def on_appointment(db: Session, org, appt, from_status: str | None, to_status: str, extra: dict | None) -> None:
    from app.services.developer_service import emit

    if from_status is None:
        emit(db, org, "appointment.created", lambda: appointment_data(db, appt))
        if to_status == "confirmed":
            emit(db, org, "appointment.confirmed", lambda: appointment_data(db, appt))
        return
    if from_status == to_status:
        if extra and extra.get("from") and extra.get("to"):
            emit(db, org, "appointment.rescheduled", lambda: {**appointment_data(db, appt), "previous_start_at": extra["from"]})
        return
    name = STATUS_EVENT.get(to_status)
    if name:
        emit(db, org, name, lambda: appointment_data(db, appt))


def on_payment(db: Session, org, payment, name: str) -> None:
    from app.services.developer_service import emit

    emit(db, org, name, lambda: payment_data(db, payment))


def on_refund(db: Session, org, refund) -> None:
    from app.services.developer_service import emit

    emit(db, org, "refund.processed", lambda: refund_data(db, refund))
