"""A few seconds of in-process caching for the public catalogue (clinic profile, services, doctors).

Every visitor of a clinic's booking page asks for the same public lists, and building them is most of the API's CPU
time under load (measured: 7-14 ms each, 100 users). The answer is cached per API process for PUBLIC_CACHE_SECONDS
(default 5) and emptied at once when this process saves a change to the catalogue; other processes catch up within
those seconds. Only public, non-personal data is cached here: never availability, prices for a booking (always
recalculated), anything about a patient, or anything behind sign-in.
"""
from __future__ import annotations

import functools
import json
import threading
import time
from collections import OrderedDict
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings

_MAX_ENTRIES = 2048
_lock = threading.Lock()
_entries: OrderedDict[tuple, tuple[float, bytes]] = OrderedDict()
_generation = 0  # bumped by every clear, so a response built before a change is never stored after it


def clear() -> None:
    global _generation
    with _lock:
        _entries.clear()
        _generation += 1


def cached(name: str):
    """Decorate a public GET endpoint whose answer depends only on its path and query parameters."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ttl = get_settings().public_cache_seconds
            if ttl <= 0:
                return func(*args, **kwargs)
            key = (name, *sorted((k, v) for k, v in kwargs.items() if isinstance(v, (str, int, float, bool, type(None)))))
            now = time.monotonic()
            with _lock:
                hit = _entries.get(key)
                if hit and hit[0] > now:
                    _entries.move_to_end(key)
                    return Response(content=hit[1], media_type="application/json")
                generation = _generation
            body = json.dumps(jsonable_encoder(func(*args, **kwargs)), separators=(",", ":"), ensure_ascii=False).encode()
            with _lock:
                if generation == _generation:
                    _entries[key] = (now + ttl, body)
                    while len(_entries) > _MAX_ENTRIES:
                        _entries.popitem(last=False)
            return Response(content=body, media_type="application/json")

        return wrapper

    return decorator


def _catalogue_types() -> tuple[type, ...]:
    from app.models import (
        Branch,
        Organization,
        OrganizationSetting,
        Professional,
        ProfessionalBranch,
        ProfessionalService,
        Service,
        ServiceCategory,
        ServicePackage,
        ServicePackageItem,
        ServicePricing,
    )

    return (Organization, OrganizationSetting, Branch, Service, ServiceCategory, ServicePackage, ServicePackageItem, ServicePricing,
            Professional, ProfessionalBranch, ProfessionalService)


@event.listens_for(Session, "after_flush")
def _note_catalogue_change(session: Session, _ctx: Any) -> None:
    types = _catalogue_types()
    if any(isinstance(o, types) for o in (*session.new, *session.dirty, *session.deleted)):
        session.info["public_cache_stale"] = True


@event.listens_for(Session, "after_commit")
def _clear_after_catalogue_change(session: Session) -> None:
    if session.info.pop("public_cache_stale", False):
        clear()


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop("public_cache_stale", None)
