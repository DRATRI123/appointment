"""Caller IP resolution shared by auditing, API-key allowlists and rate limiting."""
from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.core.config import get_settings


def _trusted_proxy(peer: str | None) -> bool:
    if not peer:
        return False
    for entry in get_settings().forwarded_allow_ips:
        if entry in ("*", peer):
            return True
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str | None:
    """X-Forwarded-For is honoured only when the direct peer is a trusted proxy (FORWARDED_ALLOW_IPS), so clients
    cannot spoof their address to bypass API-key IP allowlists or per-IP rate limits, or to pollute audit logs."""
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _trusted_proxy(peer):
        return forwarded.split(",")[0].strip()
    return peer


def rate_limit_key(request: Request) -> str:
    return client_ip(request) or "unknown"
