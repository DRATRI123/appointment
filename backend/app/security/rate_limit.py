"""Rate limiting via slowapi. Redis storage is used automatically when REDIS_URL is set."""
from __future__ import annotations

from slowapi import Limiter

from app.core.config import get_settings
from app.security.client_ip import rate_limit_key

_settings = get_settings()

limiter = Limiter(
    key_func=rate_limit_key,  # real client IP behind trusted proxies, not the proxy's own address
    default_limits=[_settings.rate_limit_default],
    storage_uri=_settings.redis_url or "memory://",
    enabled=_settings.rate_limit_enabled,
    headers_enabled=True,
    # If Redis is unreachable, keep limiting in process memory instead of failing every request.
    in_memory_fallback_enabled=True,
    swallow_errors=True,
)
