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
from app.core.logging import get_logger

log = get_logger(__name__)

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
    """Fixed one-minute window per API key.

    With REDIS_URL set the counter lives in Redis, so every API process and container shares one limit per key.
    Without Redis (or if Redis is unreachable) it counts in process memory: still a limit, just per process, and a
    Redis outage never takes the API down."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._lock = threading.Lock()
        self._windows: dict[int, _Window] = {}
        self._redis_url = redis_url
        self._redis = None
        self._redis_failed_at = 0.0

    def _client(self):
        if not self._redis_url:
            return None
        if self._redis is None and time.time() - self._redis_failed_at > 30:
            import redis

            self._redis = redis.Redis.from_url(self._redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        return self._redis

    def _hit_redis(self, client, key_id: int, minute: int) -> int:
        key = f"apikey-rate:{key_id}:{minute}"
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 120)
        return int(pipe.execute()[0])

    def hit(self, key_id: int, limit: int) -> tuple[bool, int]:
        """Returns (allowed, seconds until the window resets)."""
        now = time.time()
        minute = int(now // 60)
        retry_after = 60 - int(now % 60)
        if self._redis_url:
            try:
                client = self._client()
                if client is not None:
                    return self._hit_redis(client, key_id, minute) <= limit, retry_after
            except Exception:
                log.warning("api_keys.rate_limit_redis_unavailable")
                self._redis, self._redis_failed_at = None, time.time()
        with self._lock:
            w = self._windows.get(key_id)
            if w is None or w.minute != minute:
                w = _Window(minute, 0)
                self._windows[key_id] = w
            w.count += 1
            return w.count <= limit, retry_after

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
        if self._redis_url:
            try:
                client = self._client()
                for key in client.scan_iter("apikey-rate:*") if client is not None else ():
                    client.delete(key)
            except Exception:
                self._redis, self._redis_failed_at = None, time.time()


limiter = KeyRateLimiter(get_settings().redis_url)
