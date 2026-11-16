"""Turn domain changes into webhook events (queued in the outbox, delivered by the worker)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.webhooks.catalog import STATUS_EVENT, appointment_data, customer_data, payment_data, refund_data


def _sync(db: Session, org, entity_type: str, entity_id: int, action: str = "upsert") -> None:
    """Integration Hub connectors (CRM, accounting, Google Contacts/Drive) send the change from the worker."""
    from app.connectors.sync import enqueue

    enqueue(db, org.id, entity_type, entity_id, action)


def on_appointment(db: Session, org, appt, from_status: str | None, to_status: str, extra: dict | None) -> None:
    from app.services.developer_service import emit

    _sync(db, org, "appointment", appt.id)

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
    if name == "payment.verified":  # accounting gets verified payments only
        _sync(db, org, "payment", payment.id)


def on_refund(db: Session, org, refund) -> None:
    from app.services.developer_service import emit

    emit(db, org, "refund.processed", lambda: refund_data(db, refund))
    _sync(db, org, "refund", refund.id)


def on_customer(db: Session, org, customer, name: str) -> None:
    """customer.created / customer.updated / customer.deleted (also used for erasure on request)."""
    from app.services.developer_service import emit

    emit(db, org, name, lambda: customer_data(customer))
    _sync(db, org, "customer", customer.id, "delete" if name == "customer.deleted" else "upsert")


def on_document(db: Session, org, document, deleted: bool = False) -> None:
    _sync(db, org, "document", document.id, "delete" if deleted else "upsert")


def on_schedule(db: Session, org, professional) -> None:
    from app.services.developer_service import emit

    emit(db, org, "schedule.updated", lambda: {"professional": {"id": professional.public_id, "name": professional.display_name}})


def on_reminder(db: Session, org, appt, scheduled_for) -> None:
    from app.services.developer_service import emit

    emit(db, org, "reminder.due", lambda: {**appointment_data(db, appt), "reminder_at": scheduled_for.isoformat() if scheduled_for else None})


def on_notification_failed(db: Session, org, notification) -> None:
    from app.services.developer_service import emit

    emit(db, org, "notification.failed", lambda: {"id": notification.public_id, "event": notification.event,
                                                  "channel": notification.channel, "error": (notification.last_error or "")[:300]})
