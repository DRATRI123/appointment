"""Append-only audit trail for privileged and sensitive actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.ids import new_public_id
from app.core.time import utcnow
from app.models import AuditLog, User


@dataclass
class RequestMeta:
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


def record_audit(
    db: Session,
    *,
    action: str,
    actor: User | None,
    organization_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    purpose: str | None = None,
    meta: RequestMeta | None = None,
    actor_type: str = "user",
) -> AuditLog:
    meta = meta or RequestMeta()
    log = AuditLog(
        public_id=new_public_id(),
        organization_id=organization_id,
        actor_user_id=actor.id if actor else None,
        actor_type=actor_type if actor else "system",
        actor_label=(actor.full_name if actor else "system")[:160],
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        ip_address=meta.ip_address,
        user_agent=(meta.user_agent or "")[:512] or None,
        request_id=meta.request_id,
        purpose=purpose,
        created_at=utcnow(),
    )
    log.signature = sign_audit_row(log)
    db.add(log)
    db.flush()
    return log


SIGNED_FIELDS = ("public_id", "organization_id", "actor_user_id", "actor_type", "actor_label", "action", "entity_type", "entity_id",
                 "before", "after", "ip_address", "request_id", "purpose", "created_at")


def sign_audit_row(log: AuditLog) -> str:
    """HMAC over the row's content with the audit purpose key. Someone who can edit the database but does not have the
    server's DATA_ENCRYPTION_KEY cannot change a row (or invent one) without the signature failing verification."""
    import json

    from app.security.crypto import keyed_hash

    created = log.created_at
    payload = {f: getattr(log, f) for f in SIGNED_FIELDS}
    payload["created_at"] = created.replace(tzinfo=None).isoformat(timespec="microseconds") if created else None
    return keyed_hash(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")), "audit")
