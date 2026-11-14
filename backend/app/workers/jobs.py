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


@job("deliver_webhooks")
def deliver_webhooks() -> dict:
    from app.services.developer_service import deliver_due, purge_old_deliveries

    with session_scope() as db:
        counts = deliver_due(db)
        purge_old_deliveries(db)
    if any(counts.values()):
        log.info("jobs.deliver_webhooks", **counts)
    return counts


PERIODIC_JOBS = ("expire_holds", "expire_unpaid_appointments", "purge_expired_documents", "pull_calendar_busy", "sync_external",
                 "schedule_reminders", "dispatch_notifications", "deliver_webhooks")
