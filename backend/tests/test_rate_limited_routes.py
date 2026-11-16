"""Every rate-limited route must be able to carry the rate-limit headers.

The limiter adds X-RateLimit-* headers (``headers_enabled=True``). For a handler that returns plain data (a dict),
slowapi can only add them through a ``response: Response`` parameter; without one, every call fails with HTTP 500 once
rate limiting is on (as on every real server and development computer). The test suite turns rate limiting off, so the
API tests alone cannot see this: the integration "Test connection" buttons were broken this way.
"""
from __future__ import annotations

import inspect
import typing

from starlette.responses import Response

from app.main import app
from app.security.rate_limit import limiter
from tests.test_no_blocking_db_on_event_loop import _api_routes


def _is_response(annotation) -> bool:
    return inspect.isclass(annotation) and issubclass(annotation, Response)


def test_rate_limited_routes_can_carry_the_limit_headers():
    limited = [r for r in _api_routes(app.routes)
               if f"{r.endpoint.__module__}.{r.endpoint.__name__}" in limiter._route_limits]
    assert len(limited) > 20, "route discovery broke; the check below would pass vacuously"
    offenders = []
    for route in limited:
        fn = inspect.unwrap(route.endpoint)
        hints = typing.get_type_hints(fn, include_extras=False)
        takes_response = any(_is_response(hints.get(name)) for name in inspect.signature(fn).parameters)
        if not takes_response and not _is_response(hints.get("return")):
            offenders.append(f"{','.join(sorted(route.methods))} {route.path} ({fn.__module__}.{fn.__name__})")
    assert not offenders, "add `response: Response` to these rate-limited handlers:\n" + "\n".join(offenders)
