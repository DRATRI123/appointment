"""Security headers and request-id middleware."""
from __future__ import annotations

import re
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # A caller-supplied id is kept for tracing only if it is short and plain; anything else could forge log lines.
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.path.startswith(("/docs", "/redoc")):
            # Swagger UI needs inline scripts/styles from its CDN.
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            )
        elif request.url.path.startswith("/media/"):
            headers.setdefault("Content-Security-Policy", "default-src 'none'; img-src 'self'; frame-ancestors 'none'")
            headers.setdefault("Cache-Control", "public, max-age=86400")
        else:
            headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            if request.url.path.startswith("/api/"):
                # API answers hold personal data: never kept by the browser or a shared proxy unless an endpoint says
                # otherwise (public clinic pages set their own short cache).
                headers.setdefault("Cache-Control", "no-store")
                headers.setdefault("Pragma", "no-cache")
        if settings.cookie_secure:
            headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
