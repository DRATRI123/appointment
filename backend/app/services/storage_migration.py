"""Switch file storage (this server's disk <-> an S3-compatible bucket) without losing a file.

1. The super admin saves and tests the bucket settings, then presses "Move files and switch".
2. The worker copies every file byte for byte (private files stay encrypted exactly as they are), reads each copy back
   and compares its SHA-256 with the original. Nothing is deleted from the old storage.
3. Only when every file is copied and checked, the active storage changes. For a while, reads that miss in the new
   storage are answered from the old one (files uploaded during the last seconds of the copy), and a second pass copies
   those too.
4. "Finish" stops reading from the old storage. The old copies stay until you delete them yourself.

If any file fails, nothing is switched and the error is shown; pressing the button again continues where it stopped
(files already copied and verified are skipped).
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationFailed
from app.core.logging import get_logger
from app.core.storage import active_backend, build_backend, exists, list_keys, read_raw, reset_storage, write_raw
from app.core.time import utcnow
from app.services import platform_config as pc

log = get_logger(__name__)
STATE_KEY = "platform.storage_migration"
BACKENDS = ("local", "s3")
SLICE_SECONDS = 120  # the worker also sends reminders and messages: copy in slices, continue next cycle


class _Paused(Exception):
    pass


def state(db: Session) -> dict[str, Any]:
    from app.models import SystemSetting

    return dict(db.scalar(select(SystemSetting.value).where(SystemSetting.key == STATE_KEY)) or {"status": "idle"})


def _save_state(db: Session, value: dict[str, Any]) -> None:
    from app.models import SystemSetting

    row = db.scalar(select(SystemSetting).where(SystemSetting.key == STATE_KEY))
    if row is None:
        db.add(SystemSetting(key=STATE_KEY, value=value, description="Progress of the last file storage switch"))
    else:
        row.value = value
    db.flush()


def request_switch(db: Session, target: str, actor_id: int | None) -> dict[str, Any]:
    if target not in BACKENDS:
        raise ValidationFailed("Choose local or s3.", code="invalid_backend")
    current = active_backend()
    if target == current:
        raise ValidationFailed("This storage is already in use.", code="already_active")
    st = state(db)
    if st.get("status") in ("queued", "running"):
        raise ConflictError("A move is already in progress.", code="migration_running")
    if target == "s3":
        section = pc.section_state(db, "storage")
        if section["status"] != "connected":
            raise ValidationFailed("Save the bucket settings and press Test first. The switch needs a successful test.", code="storage_untested")
    value = {"status": "queued", "source": current, "target": target, "total": 0, "copied": 0, "skipped": 0, "failed": 0, "bytes": 0,
             "requested_at": utcnow().isoformat(), "requested_by": actor_id, "error": None}
    _save_state(db, value)
    return value


def _switch(db: Session, source: str, target: str) -> None:
    row = pc.read_row(db)
    row.values["storage_backend"] = target
    row.values["storage_previous_backend"] = source  # reads fall back to the old storage until "Finish"
    pc.write_row(db, row)
    reset_storage()


def finish(db: Session) -> None:
    """Stop reading from the old storage (after the second pass)."""
    row = pc.read_row(db)
    row.values.pop("storage_previous_backend", None)
    pc.write_row(db, row)
    st = state(db)
    st["fallback_removed_at"] = utcnow().isoformat()
    _save_state(db, st)
    reset_storage()


def _copy_all(db: Session, st: dict[str, Any], src, dst, *, commit, deadline: float) -> None:
    for key, _size in list_keys(src, ""):
        if time.monotonic() > deadline:
            raise _Paused
        if exists(dst, key):
            st["skipped"] += 1
            continue
        data = read_raw(src, key)
        write_raw(dst, key, data)
        if hashlib.sha256(read_raw(dst, key)).digest() != hashlib.sha256(data).digest():
            st["failed"] += 1
            raise RuntimeError(f"The copy of {key} does not match the original.")
        st["copied"] += 1
        st["bytes"] += len(data)
        if (st["copied"] + st["skipped"]) % 50 == 0:
            _save_state(db, dict(st))
            commit()


def run_pending(db: Session, *, commit=None, slice_seconds: float = SLICE_SECONDS) -> dict[str, Any] | None:
    """Worker step: carry out a queued switch, at most ``slice_seconds`` per call (it continues on the next call).
    ``commit`` saves progress (the worker commits; tests flush)."""
    commit = commit or db.flush
    st = state(db)
    if st.get("status") not in ("queued", "running"):
        return None
    deadline = time.monotonic() + slice_seconds
    if st.get("status") == "queued":
        st.update(status="running", started_at=utcnow().isoformat(), copied=0, skipped=0, failed=0, bytes=0, error=None)
    source, target = st["source"], st["target"]
    try:
        src, dst = build_backend(source), build_backend(target)
        if not st.get("total"):
            st["total"] = sum(1 for _ in list_keys(src, ""))
        _save_state(db, dict(st))
        commit()
        if not st.get("switched_at"):
            st["skipped"] = 0  # recounted on each pass: files copied in an earlier slice count as skipped
            _copy_all(db, st, src, dst, commit=commit, deadline=deadline)
            _switch(db, source, target)
            st["switched_at"] = utcnow().isoformat()
            _save_state(db, dict(st))
            commit()
        _copy_all(db, st, src, dst, commit=commit, deadline=deadline)  # second pass: files uploaded while the first ran
        st.update(status="done", finished_at=utcnow().isoformat())
        log.info("storage.switched", source=source, target=target, copied=st["copied"], skipped=st["skipped"])
    except _Paused:
        _save_state(db, dict(st))  # still "running": the next worker cycle continues
        commit()
        return st
    except Exception as exc:  # noqa: BLE001 - shown in the panel; nothing switched unless every file was copied
        st.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:300]}", finished_at=utcnow().isoformat())
        log.error("storage.switch_failed", source=source, target=target, error=type(exc).__name__)
    _save_state(db, dict(st))
    commit()
    return st


def usage(db: Session, limit: int = 200_000) -> dict[str, Any]:
    """Number of files and bytes in the active storage (counts stop at ``limit`` objects)."""
    backend = build_backend(active_backend())
    out = {"backend": active_backend(), "public": {"files": 0, "bytes": 0}, "private": {"files": 0, "bytes": 0}, "truncated": False}
    n = 0
    for key, size in list_keys(backend, ""):
        part = out["public"] if key.startswith("public/") else out["private"]
        part["files"] += 1
        part["bytes"] += int(size or 0)
        n += 1
        if n >= limit:
            out["truncated"] = True
            break
    return out
