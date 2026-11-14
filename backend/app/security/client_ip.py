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


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def client_ip(request: Request) -> str | None:
    """X-Forwarded-For is honoured only when the direct peer is a trusted proxy (FORWARDED_ALLOW_IPS), so clients
    cannot spoof their address to bypass API-key IP allowlists or per-IP rate limits, or to pollute audit logs.

    Proxies *append* the address they saw, and the left-most entries are whatever the client sent. So the list is read
    from the right, skipping our own trusted proxies; the first address that is not one of them is the real client."""
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _trusted_proxy(peer):
        return peer
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _valid_ip(hop):
            break  # garbage in the chain: fall back to the proxy itself rather than trust it
        if not _trusted_proxy(hop):
            return hop
    else:
        return hops[0] if hops and _valid_ip(hops[0]) else peer  # every hop is one of our proxies
    return peer


def rate_limit_key(request: Request) -> str:
    return client_ip(request) or "unknown"
