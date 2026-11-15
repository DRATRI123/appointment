"""Idempotency keys for requests that must never run twice (bookings, payment submissions).

A client sends ``Idempotency-Key: <random value>`` and repeats exactly the same request with the same key if it is not
sure the first one arrived (a timeout, a dropped mobile connection, a double tap). The first request does the work and
its response is stored; a repeat gets that stored response back (header ``Idempotent-Replayed: true``) and nothing is
booked or submitted again. Keys are scoped to the clinic, the operation and the caller, and kept for 24 hours.

* Same key, different request body: ``422 idempotency_key_reused``.
* Same key while the first request is still running (PostgreSQL only; SQLite runs writers one at a time):
  ``409 idempotency_in_progress``; retry a moment later.
* A request that fails stores nothing, so it can be retried with the same key.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.exceptions import ConflictError, ValidationFailed
from app.core.time import utcnow
from app.models import IdempotencyKey, Organization
from app.security.crypto import decrypt_text, encrypt_text

HEADER = "Idempotency-Key"
TTL = timedelta(hours=24)
_KEY = re.compile(r"^[A-Za-z0-9_.:\-]{8,100}$")


def _digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class Idempotency:
    """Use: ``idem = Idempotency.start(...)``; if ``idem.replay`` is set return it, else do the work and
    ``return idem.finish(result, status)``."""

    def __init__(self, db: Session, row: IdempotencyKey | None, replay: JSONResponse | None) -> None:
        self.db, self.row, self.replay = db, row, replay

    @classmethod
    def start(cls, db: Session, request: Request, org: Organization, *, scope: str, principal: str, payload: Any) -> Idempotency | None:
        key = request.headers.get(HEADER)
        if key is None:
            return None
        if not _KEY.match(key):
            raise ValidationFailed("Idempotency-Key must be 8-100 letters, digits or - _ . :", code="idempotency_key_invalid")
        owner = hashlib.sha256(principal.encode()).hexdigest()  # never store session keys or tokens in clear
        wanted = _digest(payload)
        found = cls._find(db, org.id, scope, owner, key)
        if found is not None:
            return cls(db, None, cls._replay(found, wanted))
        row = IdempotencyKey(organization_id=org.id, scope=scope, principal=owner, key=key, request_hash=wanted,
                             response_status=0, expires_at=utcnow() + TTL)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            # Another request with this key committed while we waited for its row lock (PostgreSQL).
            found = cls._find(db, org.id, scope, owner, key)
            if found is None or not found.response_status:
                raise ConflictError("A request with this Idempotency-Key is still being processed. Try again shortly.",
                                    code="idempotency_in_progress") from None
            return cls(db, None, cls._replay(found, wanted))
        return cls(db, row, None)

    @staticmethod
    def _find(db: Session, org_id: int, scope: str, owner: str, key: str) -> IdempotencyKey | None:
        return db.scalar(select(IdempotencyKey).where(
            IdempotencyKey.organization_id == org_id, IdempotencyKey.scope == scope, IdempotencyKey.principal == owner,
            IdempotencyKey.key == key, IdempotencyKey.expires_at > utcnow()))

    @staticmethod
    def _replay(found: IdempotencyKey, wanted: str) -> JSONResponse:
        if found.request_hash != wanted:
            raise ValidationFailed("This Idempotency-Key was already used for a different request.", code="idempotency_key_reused")
        if not found.response_status or found.response_body is None:
            raise ConflictError("A request with this Idempotency-Key is still being processed. Try again shortly.", code="idempotency_in_progress")
        return JSONResponse(json.loads(decrypt_text(found.response_body)), status_code=found.response_status, headers={"Idempotent-Replayed": "true"})

    def finish(self, result: Any, status_code: int) -> Any:
        """Store the response with the work, in the same transaction, and return the result unchanged."""
        if self.row is not None:
            self.row.response_status = status_code
            self.row.response_body = encrypt_text(json.dumps(jsonable_encoder(result), separators=(",", ":")))
        return result


def purge_expired(db: Session) -> int:
    return db.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at <= utcnow())).rowcount or 0
