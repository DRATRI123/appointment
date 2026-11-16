"""The sync queue: records that changed are marked here and pushed by the worker, never inside a booking request.

* ``enqueue`` (called by hooks after a patient, document, verified payment, refund or appointment changes) marks the
  record pending for every enabled, connected connector that syncs that kind of record. One row per record and system,
  so a record changed ten times is sent once with its latest state.
* ``process_due`` (worker) claims rows with a conditional UPDATE (parallel workers never send twice), sends them, and
  retries temporary failures with growing waits (1 min, 5 min, 30 min, 2 h, 6 h, 12 h, 24 h) up to the connector's
  retry limit; then the row is "dead" and shown in the hub with a Retry button. Credentials that were revoked stop the
  connector (status "Needs attention") instead of retrying forever.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.connectors import registry
from app.connectors.base import Adapter, Ctx
from app.core.enums import IntegrationStatus
from app.core.logging import get_logger
from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError
from app.models import Integration, IntegrationSyncItem, Organization

log = get_logger(__name__)
BACKOFF_MINUTES = [1, 5, 30, 120, 360, 720, 1440]


def adapter_for(db: Session, integ: Integration) -> Adapter:
    conn = registry.get(integ.provider)
    if conn is None:
        raise ValueError(f"Unknown connector {integ.provider}")
    module, cls = conn.adapter.split(":")
    org = db.get(Organization, integ.organization_id)
    return getattr(importlib.import_module(module), cls)(Ctx(db, org, integ))


def _active(db: Session, org_id: int, providers: list[str]) -> list[Integration]:
    if not providers:
        return []
    return list(db.scalars(select(Integration).where(Integration.organization_id == org_id, Integration.provider.in_(providers),
                                                     Integration.is_enabled.is_(True), Integration.status == IntegrationStatus.CONNECTED)).all())


def enqueue(db: Session, org_id: int, entity_type: str, entity_id: int, action: str = "upsert") -> int:
    """Mark a record for sending. Never raises into the business transaction."""
    try:
        with db.begin_nested():
            count = 0
            for integ in _active(db, org_id, registry.syncing(entity_type)):
                item = db.scalar(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id, IntegrationSyncItem.entity_type == entity_type,
                                                                   IntegrationSyncItem.entity_id == entity_id))
                if item is None:
                    if action == "delete":
                        continue  # never sent: nothing to remove
                    item = IntegrationSyncItem(organization_id=org_id, integration_id=integ.id, entity_type=entity_type, entity_id=entity_id)
                    db.add(item)
                item.action, item.status, item.attempts, item.next_attempt_at, item.last_error = action, "pending", 0, utcnow(), None
                count += 1
            db.flush()
            return count
    except Exception:  # noqa: BLE001
        log.exception("sync.enqueue_failed", entity=entity_type)
        return 0


def enqueue_all(db: Session, integ: Integration, entity_type: str) -> int:
    """'Send all existing records now' (first connection). Existing rows are reset to pending."""
    from app.models import Customer, CustomerDocument, Payment, PaymentRefund

    model = {"customer": Customer, "document": CustomerDocument, "payment": Payment, "refund": PaymentRefund}.get(entity_type)
    if model is None:
        return 0
    stmt = select(model.id).where(model.organization_id == integ.organization_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    if entity_type == "payment":
        stmt = stmt.where(model.status == "verified")
    if entity_type == "refund":
        stmt = stmt.where(model.status == "processed")
    existing = {r.entity_id: r for r in db.scalars(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id,
                                                                                      IntegrationSyncItem.entity_type == entity_type)).all()}
    now, n = utcnow(), 0
    for (eid,) in db.execute(stmt).all():
        item = existing.get(eid)
        if item is None:
            db.add(IntegrationSyncItem(organization_id=integ.organization_id, integration_id=integ.id, entity_type=entity_type, entity_id=eid,
                                       status="pending", next_attempt_at=now))
        elif item.status != "synced":
            item.status, item.attempts, item.next_attempt_at = "pending", 0, now
        n += 1
    db.flush()
    return n


def _load(db: Session, entity_type: str, entity_id: int):
    from app.models import Appointment, Customer, CustomerDocument, Payment, PaymentRefund

    model = {"customer": Customer, "document": CustomerDocument, "payment": Payment, "refund": PaymentRefund, "appointment": Appointment}[entity_type]
    return db.get(model, entity_id)


def _fingerprint(entity_type: str, obj: Any, config: dict) -> str:
    fields = {"customer": ("full_name", "mobile", "email", "address"), "appointment": ("status", "start_at", "professional_id", "service_id"),
              "payment": ("status", "verified_amount_paise"), "refund": ("status", "amount_paise"), "document": ("storage_path",)}[entity_type]
    data = {f: getattr(obj, f, None) for f in fields}
    return hashlib.sha256(json.dumps([data, {k: v for k, v in config.items() if not k.startswith("_")}], sort_keys=True, default=str).encode()).hexdigest()


def process_item(db: Session, item: IntegrationSyncItem) -> str:
    integ = db.get(Integration, item.integration_id)
    if integ is None or not integ.is_enabled or integ.status != IntegrationStatus.CONNECTED:
        item.status, item.last_error = "skipped", "The integration is switched off or disconnected."
        return item.status
    adapter = adapter_for(db, integ)
    max_attempts = int(adapter.ctx.config.get("max_attempts") or 8)
    started = time.monotonic()

    def progress(external_id: str) -> None:  # multi-step pushes (invoice, then payment) save each step at once
        item.external_id = external_id
        db.flush()

    adapter.progress = progress  # type: ignore[attr-defined]
    try:
        obj = _load(db, item.entity_type, item.entity_id)
        erased = obj is None or getattr(obj, "deleted_at", None) is not None or (item.entity_type == "customer" and (obj.metadata_ or {}).get("anonymized_at"))
        if item.action == "delete" or erased:
            if item.external_id:
                adapter.remove(item.entity_type, item.external_id)
            item.status, item.external_id, item.last_error = "synced", None, None
        else:
            fp = _fingerprint(item.entity_type, obj, adapter.ctx.config)
            if item.payload_hash == fp and item.external_id:
                item.status = "synced"  # nothing changed since the last successful send
            else:
                item.external_id = adapter.push(item.entity_type, obj, item.external_id)
                item.status, item.payload_hash, item.last_error = "synced", fp, None
        item.synced_at = integ.last_synced_at = utcnow()
        adapter.ctx.log(f"sync.{item.entity_type}", "ok", started=started, detail={"action": item.action})
    except IntegrationAPIError as exc:
        item.attempts += 1
        item.last_error = str(exc)[:1000]
        adapter.ctx.log(f"sync.{item.entity_type}", "failed", error=str(exc), started=started)
        if exc.reconnect:
            integ.status, integ.last_error = IntegrationStatus.ERROR, integ.last_error or str(exc)[:500]
            item.status, item.next_attempt_at = "failed", None  # waits for "Retry" after reconnecting
        elif (exc.retryable or exc.status is None) and item.attempts < max_attempts:
            item.status = "failed"
            item.next_attempt_at = utcnow() + timedelta(minutes=BACKOFF_MINUTES[min(item.attempts - 1, len(BACKOFF_MINUTES) - 1)])
        else:
            item.status, item.next_attempt_at = "dead", None
        integ.last_error = str(exc)[:500]
    except Exception as exc:  # noqa: BLE001 - a broken record must not stop the worker
        item.attempts += 1
        item.status, item.next_attempt_at, item.last_error = "dead", None, f"{type(exc).__name__}: {str(exc)[:300]}"
        log.exception("sync.item_failed", item=item.id)
    return item.status


def process_due(db: Session, *, limit: int = 50, commit: bool = True) -> dict[str, int]:
    now = utcnow()
    db.execute(update(IntegrationSyncItem).where(IntegrationSyncItem.status == "sending", IntegrationSyncItem.updated_at < now - timedelta(minutes=10))
               .values(status="failed", next_attempt_at=now))
    ids = db.scalars(select(IntegrationSyncItem.id).where(IntegrationSyncItem.status.in_(["pending", "failed"]), IntegrationSyncItem.next_attempt_at.is_not(None),
                                                          IntegrationSyncItem.next_attempt_at <= now)
                     .order_by(IntegrationSyncItem.next_attempt_at, IntegrationSyncItem.id).limit(limit)).all()
    counts = {"synced": 0, "failed": 0, "dead": 0, "skipped": 0}
    for iid in ids:
        claimed = db.execute(update(IntegrationSyncItem).where(IntegrationSyncItem.id == iid, IntegrationSyncItem.status.in_(["pending", "failed"]))
                             .values(status="sending", updated_at=utcnow())).rowcount
        if not claimed:
            continue
        item = db.get(IntegrationSyncItem, iid)
        db.refresh(item)
        status = process_item(db, item)
        counts[status if status in counts else "failed"] += 1
        if commit:
            db.commit()
        else:
            db.flush()
    return counts
