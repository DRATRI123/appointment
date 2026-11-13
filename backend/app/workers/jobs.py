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


PERIODIC_JOBS = ("expire_holds", "expire_unpaid_appointments", "purge_expired_documents")
