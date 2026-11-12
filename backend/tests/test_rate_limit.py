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
