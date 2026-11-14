"""Webhook signing and SSRF protection."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from app.core.config import get_settings

SIGNATURE_HEADER = "X-Webhook-Signature"


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """``t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">``"""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify(secret: str, header: str, body: bytes, *, now: int, tolerance: int = 300) -> bool:
    """Reference implementation for receivers (also used in tests)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(now - ts) > tolerance:
        return False
    expected = sign(secret, ts, body).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def private_targets_allowed() -> bool:
    s = get_settings()
    return s.webhook_allow_private_targets if s.webhook_allow_private_targets is not None else s.app_env in {"development", "test"}


Resolver = Callable[[str, int], list[str]]


def _resolve(host: str, port: int) -> list[str]:
    return list({info[4][0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})


def check_url(url: str, *, resolver: Resolver | None = None) -> str | None:
    """Returns a reason the URL may not be called, or None. Blocks non-HTTPS outside development and any address
    that resolves to loopback, private, link-local (cloud metadata), multicast or reserved ranges."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return "Use a full https:// URL."
    if parsed.username or parsed.password:
        return "Do not put credentials in the URL."
    allow_private = private_targets_allowed()
    if parsed.scheme != "https" and not allow_private:
        return "Webhook URLs must use https."
    if allow_private:
        return None
    try:
        addresses = (resolver or _resolve)(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return "The host name could not be resolved."
    for a in addresses:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return "Webhook URLs must point to a public internet address."
    return None
