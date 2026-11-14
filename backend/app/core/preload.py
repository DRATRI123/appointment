"""Batch-loading for list endpoints (avoids one query per row).

SQLAlchemy's identity map holds loaded objects weakly: if nothing references them they are discarded, and the next
``db.get()`` queries again. ``preload`` loads all needed rows of a model in one query and keeps them referenced for
the rest of the session (one request), so per-row ``db.get()`` calls in serializers become free.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def preload(db: Session, model, ids: Iterable[Any]) -> dict[Any, Any]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.scalars(select(model).where(model.id.in_(wanted))).all()
    db.info.setdefault("prefetched", []).extend(rows)
    return {r.id: r for r in rows}
