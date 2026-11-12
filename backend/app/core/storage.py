"""File storage abstraction: local disk now, S3-compatible later behind the same interface.

Public files (logos, photos, service images) live under ``public/`` and are served at ``/media``.
Private files (payment screenshots, documents) live under ``private/`` and are only served through
authenticated endpoints in later phases.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import get_settings
from app.core.exceptions import ValidationFailed

IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}
PDF_SIGNATURE = b"%PDF-"
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "application/pdf": "pdf"}


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
        if not str(path).startswith(str(self.root.resolve())):
            raise ValidationFailed("Invalid storage key.")
        return path

    def save(self, *, scope: str, visibility: str, data: bytes, mime_type: str) -> StoredFile:
        if visibility not in {"public", "private"}:
            raise ValueError("visibility must be public or private")
        digest = hashlib.sha256(data).hexdigest()
        name = secrets.token_hex(16)
        ext = EXTENSIONS.get(mime_type, "bin")
        key = f"{visibility}/{scope}/{name[:2]}/{name}.{ext}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        url = f"{self.public_url_prefix}/{key[len('public/'):]}" if visibility == "public" else None
        return StoredFile(key=key, url=url, mime_type=mime_type, size_bytes=len(data), sha256=digest)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_backend == "local":
            _storage = LocalStorage(Path(settings.storage_local_path))
        else:  # pragma: no cover - S3 adapter arrives with the production phase
            raise NotImplementedError("S3 storage backend is configured in Phase 13.")
    return _storage


def validate_upload(data: bytes, *, allowed: set[str], max_mb: int) -> str:
    if len(data) == 0:
        raise ValidationFailed("Empty file.", code="empty_file")
    if len(data) > max_mb * 1024 * 1024:
        raise ValidationFailed(f"File larger than {max_mb} MB.", code="file_too_large")
    mime = sniff_mime(data[:16])
    if mime is None or mime not in allowed:
        raise ValidationFailed("Unsupported file type. Allowed: " + ", ".join(sorted(allowed)), code="unsupported_file")
    return mime
