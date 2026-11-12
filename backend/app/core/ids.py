"""Identifier helpers: UUID public ids and human readable references."""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32, no I/L/O/U


def new_public_id() -> str:
    return str(uuid.uuid4())


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def _base32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def new_ulid() -> str:
    """Lexicographically sortable 26-char id (timestamp + randomness)."""
    ts_ms = int(datetime.now(UTC).timestamp() * 1000)
    rand = secrets.randbits(80)
    return _base32(ts_ms, 10) + _base32(rand, 16)


def new_reference(prefix: str, org_code: str | None = None) -> str:
    """Human readable unique reference such as ``APT-ACME-01HZX...`` or ``PAY-01HZX...``."""
    parts = [prefix.upper()]
    if org_code:
        parts.append(org_code.upper()[:8])
    parts.append(new_ulid())
    return "-".join(parts)
