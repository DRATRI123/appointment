"""File storage: local disk or any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, MinIO), same interface.

Public files (logos, photos, service images) live under ``public/`` and are served at ``/media``.
Private files (payment screenshots, documents) live under ``private/`` and are only streamed through
authenticated endpoints. With S3 the bucket stays private: ``/media`` is streamed by the API, so browsers never
need bucket credentials or a public bucket policy.
"""
from __future__ import annotations

import hashlib
import io
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.exceptions import ValidationFailed

IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}
PDF_SIGNATURE = b"%PDF-"
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "application/pdf": "pdf", "text/csv": "csv"}


def sniff_mime(head: bytes) -> str | None:
    for mime, sigs in IMAGE_SIGNATURES.items():
        if any(head.startswith(s) for s in sigs):
            if mime == "image/webp" and head[8:12] != b"WEBP":
                continue
            return mime
    if head.startswith(PDF_SIGNATURE):
        return "application/pdf"
    return None


@dataclass
class StoredFile:
    key: str  # storage key, e.g. public/org/<id>/ab/abcd.png
    url: str | None  # public URL when the file is public
    mime_type: str
    size_bytes: int
    sha256: str


class Storage(Protocol):
    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str) -> StoredFile: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path, public_url_prefix: str = "/media"):
        self.root = root
        self.public_url_prefix = public_url_prefix.rstrip("/")
        (self.root / "public").mkdir(parents=True, exist_ok=True)
        (self.root / "private").mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # is_relative_to, not a string prefix: "/data/uploads2" must not count as inside "/data/uploads".
        if not path.is_relative_to(self.root.resolve()):
            raise ValidationFailed("Invalid storage key.")
        return path

    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str) -> StoredFile:
        key = _new_key(scope, visibility, mime_type)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        url = f"{self.public_url_prefix}/{key[len('public/'):]}" if visibility == "public" else None
        return StoredFile(key=key, url=url, mime_type=mime_type, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


def _new_key(scope: str, visibility: str, mime_type: str) -> str:
    if visibility not in {"public", "private"}:
        raise ValueError("visibility must be public or private")
    name = secrets.token_hex(16)
    return f"{visibility}/{scope}/{name[:2]}/{name}.{EXTENSIONS.get(mime_type, 'bin')}"


class S3Storage:
    """Objects in one private bucket under an optional prefix. Files are small (uploads are capped), so reads are
    buffered in memory."""

    def __init__(self, client, bucket: str, prefix: str = "", public_url_prefix: str = "/media"):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.public_url_prefix = public_url_prefix.rstrip("/")

    def _key(self, key: str) -> str:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValidationFailed("Invalid storage key.")
        return self.prefix + key

    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str) -> StoredFile:
        key = _new_key(scope, visibility, mime_type)
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=mime_type,
                               ServerSideEncryption="AES256")
        url = f"{self.public_url_prefix}/{key[len('public/'):]}" if visibility == "public" else None
        return StoredFile(key=key, url=url, mime_type=mime_type, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def open(self, key: str) -> BinaryIO:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        return io.BytesIO(body)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


class EncryptingStorage:
    """Private files are encrypted before they reach the disk or the bucket (AES-256-GCM with the "files" purpose key)
    and decrypted when the app reads them. Public files (logos, website images) are stored as they are.
    ``StoredFile`` reports the size and SHA-256 of the original file, so checksums keep meaning the document itself."""

    def __init__(self, inner: Storage):
        self.inner = inner

    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str) -> StoredFile:
        if visibility != "private":
            return self.inner.save(scope=scope, visibility=visibility, data=data, mime_type=mime_type)
        from app.security.crypto import encrypt_bytes

        stored = self.inner.save(scope=scope, visibility=visibility, data=encrypt_bytes(data), mime_type=mime_type)
        return StoredFile(key=stored.key, url=None, mime_type=mime_type, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def open(self, key: str) -> BinaryIO:
        fh = self.inner.open(key)
        if not key.startswith("private/"):
            return fh
        from app.security.crypto import decrypt_bytes

        with fh:
            return io.BytesIO(decrypt_bytes(fh.read()))

    def read_raw(self, key: str) -> bytes:
        with self.inner.open(key) as fh:
            return fh.read()

    def write_raw(self, key: str, data: bytes) -> None:
        """Replace a stored file in place (key rotation / first-time encryption). Same key, same location."""
        write_raw(self.inner.active if isinstance(self.inner, FallbackStorage) else self.inner, key, data)

    def private_keys(self):
        """Every stored private file key (for rotation)."""
        inner = self.inner.active if isinstance(self.inner, FallbackStorage) else self.inner
        for key, _size in list_keys(inner, "private/"):
            yield key

    def delete(self, key: str) -> None:
        self.inner.delete(key)

    def __getattr__(self, name):  # public_url_prefix, root, ... of the wrapped backend
        return getattr(self.inner, name)


class FallbackStorage:
    """Right after a switch (local -> S3 or back), files copied in the last moments may still exist only in the old place.
    Reads try the active storage first and then the previous one; writes and deletes go to the active one."""

    def __init__(self, active, previous):
        self.active, self.previous = active, previous

    def save(self, **kw) -> StoredFile:
        return self.active.save(**kw)

    def open(self, key: str) -> BinaryIO:
        try:
            return self.active.open(key)
        except (FileNotFoundError, OSError):
            return self.previous.open(key)

    def delete(self, key: str) -> None:
        self.active.delete(key)
        try:
            self.previous.delete(key)
        except Exception as exc:  # noqa: BLE001 - best effort on the old copy
            from app.core.logging import get_logger

            get_logger(__name__).warning("storage.previous_delete_failed", error=type(exc).__name__)

    def __getattr__(self, name):
        return getattr(self.active, name)


STORAGE_FIELDS = ("storage_backend", "storage_local_path", "s3_bucket", "s3_region", "s3_endpoint_url", "s3_access_key_id",
                  "s3_secret_access_key", "s3_prefix")

_storage: Storage | None = None
_storage_fp: str | None = None


def s3_client(cfg=None):
    """A boto3 S3 client from the effective settings (panel values win over .env), or from ``cfg``."""
    import boto3
    from botocore.config import Config

    from app.services.platform_config import runtime_settings

    c = cfg or runtime_settings()
    return boto3.client("s3", region_name=c.s3_region or None, endpoint_url=c.s3_endpoint_url or None,
                        aws_access_key_id=c.s3_access_key_id or None, aws_secret_access_key=c.s3_secret_access_key or None,
                        config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3, "mode": "standard"}))


def build_backend(backend: str):
    from app.services.platform_config import runtime_settings

    c = runtime_settings()
    if backend == "local":
        return LocalStorage(Path(c.storage_local_path))
    return S3Storage(s3_client(), c.s3_bucket or "", c.s3_prefix or "")


def active_backend() -> str:
    from app.services.platform_config import value

    return value("storage_backend") or "local"


def get_storage() -> Storage:
    """The active storage. Rebuilt automatically when the storage settings change (panel or .env)."""
    global _storage, _storage_fp
    from app.services.platform_config import fingerprint, overrides

    fp = fingerprint(STORAGE_FIELDS) + str(overrides().get("storage_previous_backend"))
    if _storage is None or (_storage_fp is not None and fp != _storage_fp):  # a storage set directly (tests) is kept
        backend = active_backend()
        inner = build_backend(backend)
        previous = overrides().get("storage_previous_backend")
        if previous and previous != backend:
            inner = FallbackStorage(inner, build_backend(previous))
        _storage, _storage_fp = EncryptingStorage(inner), fp
    return _storage


def reset_storage() -> None:
    global _storage, _storage_fp
    _storage, _storage_fp = None, None


def list_keys(backend, prefix: str = ""):
    """(key, stored size) for every object under ``prefix`` ("public/", "private/" or "" for all)."""
    if isinstance(backend, LocalStorage):
        root = backend.root
        base = root / prefix if prefix else root
        if not base.exists():
            return
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                yield str(path.relative_to(root)).replace("\\", "/"), path.stat().st_size
    else:
        paginator = backend.client.get_paginator("list_objects_v2")
        start = backend._key(prefix)
        for page in paginator.paginate(Bucket=backend.bucket, Prefix=start):
            for obj in page.get("Contents", []):
                key = obj["Key"][len(backend._key("")):]
                if key.startswith(("public/", "private/")):
                    yield key, obj.get("Size", 0)


def read_raw(backend, key: str) -> bytes:
    with backend.open(key) as fh:
        return fh.read()


def write_raw(backend, key: str, data: bytes) -> None:
    """Store bytes under exactly this key (copies between storages, key rotation)."""
    if isinstance(backend, LocalStorage):
        path = backend._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    else:
        backend.client.put_object(Bucket=backend.bucket, Key=backend._key(key), Body=data, ServerSideEncryption="AES256")


def exists(backend, key: str) -> bool:
    if isinstance(backend, LocalStorage):
        return backend._path(key).is_file()
    try:
        backend.client.head_object(Bucket=backend.bucket, Key=backend._key(key))
        return True
    except Exception:  # noqa: BLE001 - botocore ClientError 404
        return False


def validate_upload(data: bytes, *, allowed: set[str], max_mb: int) -> str:
    if len(data) == 0:
        raise ValidationFailed("Empty file.", code="empty_file")
    if len(data) > max_mb * 1024 * 1024:
        raise ValidationFailed(f"File larger than {max_mb} MB.", code="file_too_large")
    mime = sniff_mime(data[:16])
    if mime is None or mime not in allowed:
        raise ValidationFailed("Unsupported file type. Allowed: " + ", ".join(sorted(allowed)), code="unsupported_file")
    from app.core.virus_scan import scan_upload

    scan_upload(data)  # optional ClamAV check (UPLOAD_SCANNER=clamav); fails closed
    return mime


async def media_from_bucket(request):
    """Serve ``public/<path>`` at /media/<path> from the active storage (this server's disk or the bucket). Nothing
    outside public/ is reachable."""
    import mimetypes

    from starlette.concurrency import run_in_threadpool
    from starlette.responses import FileResponse, Response

    path = request.path_params["path"]
    if not path or ".." in path.split("/") or path.startswith("/") or "\\" in path:
        return Response(status_code=404)
    storage = get_storage()
    inner = getattr(storage, "inner", storage)
    local = inner if isinstance(inner, LocalStorage) else None
    headers = {"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"}
    if local is not None:
        try:
            file_path = local._path(f"public/{path}")
        except ValidationFailed:
            return Response(status_code=404)
        if not file_path.is_file():
            return Response(status_code=404)
        return FileResponse(file_path, headers=headers)
    try:
        fh = await run_in_threadpool(storage.open, f"public/{path}")
    except (FileNotFoundError, ValidationFailed, OSError):
        return Response(status_code=404)
    except Exception:  # noqa: BLE001 - botocore NoSuchKey / access errors: a missing image, never a 500 page
        return Response(status_code=404)
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Response(fh.read(), media_type=mime, headers=headers)
