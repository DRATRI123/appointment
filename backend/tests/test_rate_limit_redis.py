"""API-key rate limiting shared through Redis, and falling back safely when Redis is down."""
from __future__ import annotations

import os

import pytest

from app.security.api_keys import KeyRateLimiter

REDIS = os.environ.get("TEST_REDIS_URL")


@pytest.mark.skipif(not REDIS, reason="set TEST_REDIS_URL to a scratch Redis database")
def test_two_processes_share_one_limit_through_redis():
    a, b = KeyRateLimiter(REDIS), KeyRateLimiter(REDIS)  # e.g. two API containers
    a.reset()
    results = [a.hit(42, 4)[0], b.hit(42, 4)[0], a.hit(42, 4)[0], b.hit(42, 4)[0], a.hit(42, 4)[0]]
    assert results == [True, True, True, True, False]
    assert b.hit(43, 4)[0] is True  # other keys are counted separately
    a.reset()
    assert b.hit(42, 4)[0] is True


def test_unreachable_redis_falls_back_to_counting_in_memory():
    limiter = KeyRateLimiter("redis://127.0.0.1:1/0")  # nothing listens on port 1
    allowed = [limiter.hit(7, 2)[0] for _ in range(3)]
    assert allowed == [True, True, False]  # still limited, and no exception reached the request


def test_memory_limiter_without_redis():
    limiter = KeyRateLimiter(None)
    assert [limiter.hit(1, 1)[0], limiter.hit(1, 1)[0]] == [True, False]
    ok, retry = limiter.hit(2, 1)
    assert ok and 1 <= retry <= 60
