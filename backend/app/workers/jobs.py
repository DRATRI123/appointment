"""Background jobs. Registered with the queue abstraction and runnable from the CLI runner."""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import Organization
from app.workers.queue import job

log = get_logger(__name__)


@job("expire_holds")
def expire_holds() -> int:
    from app.services.availability_service import AvailabilityService

    total = 0
    with session_scope() as db:
        for org in db.scalars(select(Organization).where(Organization.deleted_at.is_(None))).all():
            total += AvailabilityService(db, org).expire_stale_holds()
    log.info("jobs.expire_holds", expired=total)
    return total


@job("expire_unpaid_appointments")
def expire_unpaid() -> int:
    from app.services.appointment_service import expire_unpaid_appointments

    with session_scope() as db:
        count = expire_unpaid_appointments(db)
    log.info("jobs.expire_unpaid_appointments", expired=count)
    return count


@job("purge_expired_documents")
def purge_documents() -> int:
    from app.services.customer_management_service import purge_expired_documents

    with session_scope() as db:
        count = purge_expired_documents(db)
    log.info("jobs.purge_expired_documents", purged=count)
    return count


@job("schedule_reminders")
def reminders() -> int:
    from app.services.notification_service import schedule_reminders

    with session_scope() as db:
        count = schedule_reminders(db)
    log.info("jobs.schedule_reminders", created=count)
    return count


@job("dispatch_notifications")
def dispatch_notifications() -> dict:
    from app.services.notification_service import dispatch_due

    with session_scope() as db:
        counts = dispatch_due(db)
    if any(counts.values()):
        log.info("jobs.dispatch_notifications", **counts)
    return counts


@job("sync_external")
def sync_external_job() -> dict:
    from app.services.integration_service import sync_external

    with session_scope() as db:
        counts = sync_external(db)
    if any(counts.values()):
        log.info("jobs.sync_external", **counts)
    return counts


@job("pull_calendar_busy")
def pull_calendar_busy() -> int:
    from app.services.integration_service import pull_all_busy

    with session_scope() as db:
        return pull_all_busy(db)


@job("purge_idempotency_keys")
def purge_idempotency_keys() -> int:
    from app.services.idempotency import purge_expired

    with session_scope() as db:
        return purge_expired(db)


@job("close_stale_requests")
def close_stale_requests() -> int:
    """Help desk: resolve requests left waiting for the patient, close resolved ones (each clinic's auto_close_days)."""
    from app.services.helpdesk_service import close_stale

    with session_scope() as db:
        return close_stale(db)


@job("deliver_webhooks")
def deliver_webhooks() -> dict:
    from app.services.developer_service import deliver_due, purge_old_deliveries

    with session_scope() as db:
        counts = deliver_due(db)
        purge_old_deliveries(db)
    if any(counts.values()):
        log.info("jobs.deliver_webhooks", **counts)
    return counts


@job("sync_integrations")
def sync_integrations() -> dict:
    """Integration Hub: send changed patients, documents, verified payments, refunds and appointments to CRM,
    accounting and Google (with retries). Also removes old integration logs."""
    from datetime import timedelta

    from sqlalchemy import delete

    from app.connectors.sync import process_due
    from app.core.time import utcnow
    from app.models import ApiAccessLog, IntegrationLog

    with session_scope() as db:
        counts = process_due(db)
        cutoff = utcnow() - timedelta(days=30)
        db.execute(delete(IntegrationLog).where(IntegrationLog.created_at < cutoff))
        db.execute(delete(ApiAccessLog).where(ApiAccessLog.created_at < cutoff))
    if any(counts.values()):
        log.info("jobs.sync_integrations", **counts)
    return counts


@job("storage_switch")
def storage_switch() -> dict | None:
    """Carry out a file-storage switch requested in Super admin -> Integrations (copy, verify, then switch)."""
    from app.services import clinic_storage
    from app.services.storage_migration import run_pending

    with session_scope() as db:
        result = run_pending(db, commit=db.commit)
        clinic_storage.run_pending(db, commit=db.commit)  # clinics moving files to (or from) their own bucket
        return result


PERIODIC_JOBS = ("expire_holds", "expire_unpaid_appointments", "purge_expired_documents", "pull_calendar_busy", "sync_external",
                 "schedule_reminders", "dispatch_notifications", "deliver_webhooks", "purge_idempotency_keys", "sync_integrations", "storage_switch",
                 "close_stale_requests")
