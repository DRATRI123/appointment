"""A clinic's own S3-compatible bucket for its private files (patient documents, payment screenshots, refund proofs,
form attachments, bank statements). Optional: clinics without one use the platform's storage.

* Every private file's key contains the clinic's id (``private/org/<clinic id>/…``), so the router can send it to the
  right place. Public images (logo, website photos) always stay on the platform storage, which serves /media.
* Files are still AES-256-GCM encrypted by this app before upload: the clinic's bucket only ever holds ciphertext.
* Switching on: the worker copies this clinic's private files from the platform storage to its bucket, reads each copy
  back and compares checksums, and only then routes the clinic's files there. Switching off copies them back first.
  Reads that miss in the clinic's bucket are answered from the platform copy (files are never deleted by a move).
* The clinic is responsible for its bucket's backups (bucket versioning); platform backups do not include it.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Any

from sqlalchemy import select

from app.core.enums import IntegrationStatus
from app.core.exceptions import ConflictError, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow

log = get_logger(__name__)
KEY = "own_storage"
REFRESH_SECONDS = 10
SLICE_SECONDS = 120
_ORG_IN_KEY = re.compile(r"^private/org/([0-9a-f-]{36})/")
_ORG_IN_SCOPE = re.compile(r"^org/([0-9a-f-]{36})(/|$)")

_lock = threading.Lock()
_state: dict[str, Any] = {"configs": {}, "backends": {}, "loaded_at": 0.0}


def client_for(cfg: dict[str, Any], secrets: dict[str, Any]):
    import boto3
    from botocore.config import Config

    return boto3.client("s3", region_name=cfg.get("s3_region") or None, endpoint_url=cfg.get("s3_endpoint_url") or None,
                        aws_access_key_id=cfg.get("s3_access_key_id") or None, aws_secret_access_key=secrets.get("s3_secret_access_key") or None,
                        config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3, "mode": "standard"}))


def backend_for(cfg: dict[str, Any], secrets: dict[str, Any]):
    from app.core.storage import S3Storage

    return S3Storage(client_for(cfg, secrets), cfg.get("s3_bucket") or "", cfg.get("s3_prefix") or "")


def _rows(db):
    from app.models import Integration, Organization

    return db.execute(select(Integration, Organization.public_id).join(Organization, Organization.id == Integration.organization_id)
                      .where(Integration.provider == KEY, Integration.professional_id.is_(None))).all()


def _load(db) -> None:
    """Clinics whose files are routed to their own bucket right now."""
    import json

    from app.security.crypto import decrypt_text

    configs = {}
    for integ, org_pid in _rows(db):
        cfg = integ.config or {}
        if integ.is_enabled and integ.status == IntegrationStatus.CONNECTED and cfg.get("_active") and integ.credentials_encrypted:
            configs[org_pid] = (cfg, json.loads(decrypt_text(integ.credentials_encrypted)))
    with _lock:
        _state["configs"], _state["loaded_at"] = configs, time.monotonic()
        _state["backends"] = {k: v for k, v in _state["backends"].items() if k in configs and v[0] == _fp(*configs[k])}


def _fp(cfg, secrets) -> str:
    keys = ("s3_bucket", "s3_region", "s3_endpoint_url", "s3_prefix", "s3_access_key_id")
    return hashlib.sha256(repr(([cfg.get(k) for k in keys], secrets.get("s3_secret_access_key"))).encode()).hexdigest()


def refresh_from(db) -> None:
    _load(db)


def reset_cache() -> None:
    with _lock:
        _state.update(configs={}, backends={}, loaded_at=0.0)


def _auto_refresh() -> bool:
    from app.core.config import get_settings

    return get_settings().app_env != "test"


def active_backend_for(org_pid: str | None):
    if not org_pid:
        return None
    if _auto_refresh() and time.monotonic() - _state["loaded_at"] > REFRESH_SECONDS:
        try:
            from app.core.database import ReadSessionLocal  # never the write engine (SQLite BEGIN IMMEDIATE)

            with ReadSessionLocal() as s:
                _load(s)
        except Exception:  # noqa: BLE001 - database not ready: platform storage only
            _state["loaded_at"] = time.monotonic()
    entry = _state["configs"].get(org_pid)
    if entry is None:
        return None
    fp = _fp(*entry)
    cached = _state["backends"].get(org_pid)
    if cached is None or cached[0] != fp:
        cached = (fp, backend_for(*entry))
        _state["backends"][org_pid] = cached
    return cached[1]


class OrgRoutingStorage:
    """Sends each clinic's private files to the clinic's own bucket when it has one; everything else to the platform."""

    def __init__(self, default):
        self.default = default

    @staticmethod
    def org_of_key(key: str) -> str | None:
        m = _ORG_IN_KEY.match(key or "")
        return m.group(1) if m else None

    def backend_for_key(self, key: str):
        return active_backend_for(self.org_of_key(key))

    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str):
        m = _ORG_IN_SCOPE.match(scope or "")
        own = active_backend_for(m.group(1)) if (m and visibility == "private") else None
        return (own or self.default).save(scope=scope, visibility=visibility, data=data, mime_type=mime_type)

    def open(self, key: str):
        own = self.backend_for_key(key)
        if own is not None:
            try:
                return own.open(key)
            except Exception as exc:  # noqa: BLE001 - not moved yet, or the clinic's bucket is unreachable: the platform copy
                log.warning("clinic_storage.read_fallback", error=type(exc).__name__)
        return self.default.open(key)

    def delete(self, key: str) -> None:
        own = self.backend_for_key(key)
        if own is not None:
            own.delete(key)
        try:
            self.default.delete(key)  # the platform copy kept by a move
        except Exception as exc:  # noqa: BLE001
            log.warning("clinic_storage.platform_delete_failed", error=type(exc).__name__)

    def write_backend(self, key: str):
        from app.core.storage import FallbackStorage

        return self.backend_for_key(key) or (self.default.active if isinstance(self.default, FallbackStorage) else self.default)

    def all_backends(self):
        from app.core.storage import FallbackStorage

        yield self.default.active if isinstance(self.default, FallbackStorage) else self.default
        for org_pid in list(_state["configs"]):
            b = active_backend_for(org_pid)
            if b is not None:
                yield b

    def __getattr__(self, name):
        return getattr(self.default, name)


# ------------------------------------------------------------------------------------------------------------- moves
def _row(db, org):
    from app.models import Integration

    return db.scalar(select(Integration).where(Integration.organization_id == org.id, Integration.provider == KEY, Integration.professional_id.is_(None)))


def request_switch(db, org, *, on: bool) -> dict[str, Any]:
    row = _row(db, org)
    if row is None or row.status != IntegrationStatus.CONNECTED or not row.is_enabled:
        raise ValidationFailed("Save the bucket settings and pass the test first.", code="storage_untested")
    cfg = dict(row.config or {})
    if bool(cfg.get("_active")) == on:
        raise ValidationFailed("Already in use." if on else "Already using the platform storage.", code="already_active")
    if (cfg.get("_migration") or {}).get("status") in ("queued", "running"):
        raise ConflictError("A move is already in progress.", code="migration_running")
    cfg["_migration"] = {"status": "queued", "direction": "to_clinic" if on else "to_platform", "total": 0, "copied": 0, "skipped": 0,
                         "bytes": 0, "error": None, "requested_at": utcnow().isoformat()}
    row.config = cfg
    db.flush()
    return cfg["_migration"]


def _platform_backend():
    from app.core.storage import active_backend, build_backend

    return build_backend(active_backend())


def run_one(db, row, org_pid: str, *, commit, slice_seconds: float = SLICE_SECONDS) -> dict[str, Any]:
    import json

    from app.core.storage import exists, list_keys, read_raw, write_raw
    from app.security.crypto import decrypt_text

    cfg = dict(row.config or {})
    st = dict(cfg.get("_migration") or {})
    if st.get("status") == "queued":
        st.update(status="running", started_at=utcnow().isoformat(), copied=0, skipped=0, bytes=0, error=None)
    deadline = time.monotonic() + slice_seconds
    secrets = json.loads(decrypt_text(row.credentials_encrypted)) if row.credentials_encrypted else {}
    clinic = backend_for(cfg, secrets)
    platform = _platform_backend()
    src, dst = (platform, clinic) if st["direction"] == "to_clinic" else (clinic, platform)
    prefix = f"private/org/{org_pid}/"

    def save(**extra):
        cfg2 = dict(row.config or {})
        cfg2["_migration"] = {**st, **extra}
        row.config = cfg2
        commit()

    try:
        keys = [k for k, _ in list_keys(src, prefix)]
        st["total"] = len(keys)
        st["skipped"] = 0
        for key in keys:
            if time.monotonic() > deadline:
                save()
                return st
            if exists(dst, key):
                st["skipped"] += 1
                continue
            data = read_raw(src, key)
            write_raw(dst, key, data)
            if hashlib.sha256(read_raw(dst, key)).digest() != hashlib.sha256(data).digest():
                raise RuntimeError(f"The copy of {key} does not match the original.")
            st["copied"] += 1
            st["bytes"] += len(data)
        cfg = dict(row.config or {})
        cfg["_active"] = st["direction"] == "to_clinic"
        st.update(status="done", finished_at=utcnow().isoformat())
        cfg["_migration"] = st
        row.config = cfg
        commit()
        refresh_from(db)
        log.info("clinic_storage.switched", direction=st["direction"], copied=st["copied"])
    except Exception as exc:  # noqa: BLE001 - shown on the integration page; nothing switched
        st.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:300]}", finished_at=utcnow().isoformat())
        save()
    return st


def run_pending(db, *, commit=None) -> int:
    """Worker step: carry out queued per-clinic moves (one time slice each)."""
    commit = commit or db.flush
    n = 0
    for row, org_pid in _rows(db):
        if ((row.config or {}).get("_migration") or {}).get("status") in ("queued", "running"):
            run_one(db, row, org_pid, commit=commit)
            n += 1
    return n


def usage(db, org) -> dict[str, Any]:
    import json

    from app.core.storage import list_keys
    from app.security.crypto import decrypt_text

    row = _row(db, org)
    active = bool(row and (row.config or {}).get("_active"))
    if active:
        backend = backend_for(row.config or {}, json.loads(decrypt_text(row.credentials_encrypted)))
    else:
        backend = _platform_backend()
    files = size = 0
    for _k, s in list_keys(backend, f"private/org/{org.public_id}/"):
        files += 1
        size += int(s or 0)
    return {"where": "clinic bucket" if active else "platform storage", "files": files, "bytes": size}
