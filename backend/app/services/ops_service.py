"""Operational state: worker heartbeat, last run of each background job, last backup.

Stored in ``system_settings`` (one row per key) so it survives restarts and every API process sees the same
values. Health checks, the Prometheus endpoint and the platform "System status" page all read from here.
"""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import NotificationStatus, PaymentStatus, WebhookDeliveryStatus
from app.core.time import utcnow
from app.models import Notification, Payment, SystemSetting, WebhookEvent

HEARTBEAT_KEY = "ops.worker.heartbeat"
JOB_KEY_PREFIX = "ops.job."
BACKUP_KEY = "ops.backup.last"

# How long without a heartbeat / backup before the status turns to "attention".
WORKER_STALE_AFTER = timedelta(minutes=5)
BACKUP_STALE_AFTER = timedelta(hours=26)  # daily backups plus a little slack


def _put(db: Session, key: str, value: dict[str, Any]) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        db.add(SystemSetting(key=key, value=value, description="Operational state (written by the worker / backup script)"))
    else:
        row.value = value
    db.flush()


def _get(db: Session, key: str) -> dict[str, Any] | None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return row.value if row else None


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def record_heartbeat(db: Session, *, interval_seconds: int) -> None:
    _put(db, HEARTBEAT_KEY, {
        "at": utcnow().isoformat(), "host": socket.gethostname(), "pid": os.getpid(),
        "interval_seconds": interval_seconds, "version": get_settings().app_version,
    })


def worker_alive(db: Session, *, interval_seconds: int) -> bool:
    """For the container health check: the worker finished a cycle recently (3 intervals, at least 2 minutes)."""
    hb = _get(db, HEARTBEAT_KEY)
    hb_at = _parse(hb.get("at")) if hb else None
    return bool(hb_at and utcnow() - hb_at <= timedelta(seconds=max(120, 3 * interval_seconds)))


def record_job(db: Session, name: str, *, ok: bool, duration_ms: int, result: Any = None, error: str | None = None) -> None:
    previous = _get(db, JOB_KEY_PREFIX + name) or {}
    now = utcnow().isoformat()
    _put(db, JOB_KEY_PREFIX + name, {
        "last_run_at": now,
        "last_success_at": now if ok else previous.get("last_success_at"),
        "last_error": None if ok else (error or "failed")[:500],
        "last_error_at": previous.get("last_error_at") if ok else now,
        "consecutive_failures": 0 if ok else int(previous.get("consecutive_failures", 0)) + 1,
        "duration_ms": duration_ms,
        "result": result if isinstance(result, (int, dict)) else None,
        "runs": int(previous.get("runs", 0)) + 1,
        "failures": int(previous.get("failures", 0)) + (0 if ok else 1),
    })


def record_backup(db: Session, info: dict[str, Any]) -> None:
    _put(db, BACKUP_KEY, {**info, "at": utcnow().isoformat()})


def system_status(db: Session) -> dict[str, Any]:
    """Everything an operator needs to know at a glance. Never includes personal data."""
    now = utcnow()
    hb = _get(db, HEARTBEAT_KEY)
    hb_at = _parse(hb.get("at")) if hb else None
    worker_ok = bool(hb_at and now - hb_at <= WORKER_STALE_AFTER)

    jobs = {}
    for row in db.scalars(select(SystemSetting).where(SystemSetting.key.like(JOB_KEY_PREFIX + "%"))).all():
        jobs[row.key[len(JOB_KEY_PREFIX):]] = row.value or {}
    failing_jobs = sorted(name for name, j in jobs.items() if int(j.get("consecutive_failures", 0)) >= 3)

    backup = _get(db, BACKUP_KEY)
    backup_at = _parse(backup.get("at")) if backup else None
    backup_ok = bool(backup_at and now - backup_at <= BACKUP_STALE_AFTER and backup.get("ok", True))

    def count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    backlog = {
        # Due now (future reminders are "scheduled" and not a backlog).
        "notifications_pending": count(select(func.count()).select_from(Notification).where(
            Notification.status.in_([NotificationStatus.PENDING, NotificationStatus.SENDING]),
            (Notification.scheduled_for.is_(None)) | (Notification.scheduled_for <= now))),
        "notifications_failed": count(select(func.count()).select_from(Notification).where(Notification.status == NotificationStatus.FAILED)),
        "webhooks_pending": count(select(func.count()).select_from(WebhookEvent).where(
            WebhookEvent.status.in_([WebhookDeliveryStatus.PENDING, WebhookDeliveryStatus.RETRYING]))),
        "webhooks_failed": count(select(func.count()).select_from(WebhookEvent).where(
            WebhookEvent.status.in_([WebhookDeliveryStatus.FAILED, WebhookDeliveryStatus.DEAD]))),
        "payments_awaiting_verification": count(select(func.count()).select_from(Payment).where(
            Payment.status.in_([PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW]))),
    }
    oldest = db.scalar(select(func.min(Payment.updated_at)).where(Payment.status.in_([PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW])))
    backlog["oldest_unverified_payment_minutes"] = int((now - oldest).total_seconds() // 60) if oldest else 0

    attention = []
    if not worker_ok:
        attention.append("The background worker has not reported in the last 5 minutes: reminders, messages and webhooks are not being sent.")
    if failing_jobs:
        attention.append("Background jobs failing repeatedly: " + ", ".join(failing_jobs))
    if not backup_ok:
        attention.append("No successful backup in the last 26 hours.")
    return {
        "status": "ok" if not attention else "attention",
        "attention": attention,
        "checked_at": now.isoformat(),
        "version": get_settings().app_version,
        "environment": get_settings().app_env,
        "worker": {"ok": worker_ok, "last_heartbeat_at": hb_at.isoformat() if hb_at else None,
                   "host": hb.get("host") if hb else None, "interval_seconds": hb.get("interval_seconds") if hb else None},
        "jobs": jobs,
        "backup": {"ok": backup_ok, **(backup or {})},
        "backlog": backlog,
    }
