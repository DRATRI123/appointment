"""Rate limiting must work when enabled (the rest of the suite runs with it disabled)."""
from __future__ import annotations

import pytest

from app.security.rate_limit import limiter


@pytest.fixture()
def limited_client(client):
    limiter.enabled = True
    limiter.reset()
    try:
        yield client
    finally:
        limiter.enabled = False
        limiter.reset()


def test_otp_request_is_rate_limited_with_headers(limited_client):
    numbers = [f"97000000{i:02d}" for i in range(6)]
    statuses = []
    for n in numbers:
        r = limited_client.post("/api/v1/auth/otp/request", json={"identifier": n})
        statuses.append(r.status_code)
        if r.status_code == 200:
            assert "X-RateLimit-Limit" in r.headers
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_rate_limited_routes_still_return_bodies(limited_client):
    r = limited_client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    r = limited_client.post("/api/v1/auth/password/reset", json={"token": "x" * 20, "new_password": "Str0ngPass123"})
    assert r.status_code == 401


def test_every_rate_limited_route_declares_a_response_parameter():
    """slowapi injects rate-limit headers through a `response: Response` parameter; a route without it
    raises at runtime only when limiting is enabled, which the rest of the suite does not exercise."""
    import inspect

    from app.main import create_app

    app = create_app()
    limited = set(limiter._route_limits)  # keys like "app.api.v1.auth.request_otp"
    missing = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        key = f"{endpoint.__module__}.{endpoint.__name__}"
        if key in limited and "response" not in inspect.signature(endpoint).parameters:
            missing.append(key)
    assert not limited or missing == [], missing
    assert len(limited) >= 10  # sanity: the decorator registry is populated


def test_public_booking_routes_work_with_limiter_enabled(limited_client):
    from tests.booking_helpers import Clinic, ist

    c = Clinic(limited_client, email="rl-owner@example.com", name="RL Clinic", payment_mode="pay_at_clinic")
    hold = c.public_hold(ist(c.monday, 9))
    assert "X-RateLimit-Limit" not in hold  # body is the hold, headers live on the response
    appt = c.public_book(hold["id"])
    assert appt["status"] == "confirmed"
