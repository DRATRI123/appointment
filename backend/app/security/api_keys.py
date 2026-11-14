"""Developer API keys.

Format: ``ak_live_<8-char id>_<40-char secret>``. Only an HMAC-SHA256 of the whole key (peppered with SECRET_KEY)
is stored; the plaintext is shown once at creation. A key acts as its creator inside one organization, limited to
the intersection of its scopes and the creator's current permissions, and only on the paths listed below.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import threading
import time
from dataclasses import dataclass

from app.core.config import get_settings

PREFIX = "ak_live_"

# Scopes a key may hold. Deliberately excludes payment recording/verification, refunds, roles, staff, settings,
# integrations and key management: an API key can never mark money as received or widen access.
API_SCOPES: dict[str, str] = {
    "appointments:read": "Read appointments and availability",
    "appointments:write": "Create, reschedule and cancel appointments",
    "appointments:checkin": "Check in, start and complete appointments",
    "customers:read": "Read customers",
    "customers:write": "Create and update customers",
    "services:read": "Read services, categories and packages",
    "branches:read": "Read branches",
    "professionals:read": "Read professionals and schedules",
    "payments:read": "Read payment status (never record or verify payments)",
    "booking_forms:read": "Read booking forms",
    "reports:read": "Read dashboards and reports",
}

# First path segment after /api/v1 that keys may call. Matched as a whole segment ("customers" ≠ "customer").
ALLOWED_SEGMENTS = {"appointments", "availability", "branches", "professionals", "services", "service-categories", "service-packages",
                    "customers", "payments", "waitlist", "booking-forms", "reports", "analytics", "schedules"}


def looks_like_key(token: str | None) -> bool:
    return bool(token) and token.startswith(PREFIX)


def generate() -> tuple[str, str]:
    """Returns (plaintext key, display prefix)."""
    ident = secrets.token_hex(4)
    key = f"{PREFIX}{ident}_{secrets.token_urlsafe(30)}"
    return key, f"{PREFIX}{ident}"


def hash_key(key: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), key.encode(), hashlib.sha256).hexdigest()


def display_prefix(key: str) -> str:
    return key[: len(PREFIX) + 8]


def path_allowed(path: str, api_prefix: str) -> bool:
    if not path.startswith(api_prefix + "/"):
        return False
    segment = path[len(api_prefix) + 1:].split("/", 1)[0]
    return segment in ALLOWED_SEGMENTS


def ip_allowed(ip: str | None, allowed: list[str] | None) -> bool:
    if not allowed:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def validate_cidrs(entries: list[str]) -> list[str]:
    out = []
    for e in entries:
        e = e.strip()
        if not e:
            continue
        try:
            out.append(str(ipaddress.ip_network(e, strict=False)))
        except ValueError as exc:
            raise ValueError(f"Not an IP address or CIDR range: {e}") from exc
    return out


@dataclass
class _Window:
    minute: int
    count: int


class KeyRateLimiter:
    """Fixed one-minute window per key, in process memory. Multi-instance deployments should front this with Redis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[int, _Window] = {}

    def hit(self, key_id: int, limit: int) -> tuple[bool, int]:
        """Returns (allowed, seconds until the window resets)."""
        now = time.time()
        minute = int(now // 60)
        with self._lock:
            w = self._windows.get(key_id)
            if w is None or w.minute != minute:
                w = _Window(minute, 0)
                self._windows[key_id] = w
            w.count += 1
            return w.count <= limit, 60 - int(now % 60)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = KeyRateLimiter()
