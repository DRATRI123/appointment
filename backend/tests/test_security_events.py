"""Security events are counted for alerting (without personal data), and sample data never reaches a server."""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.observability import REGISTRY
from tests.helpers import register


def _count(event: str) -> float:
    return REGISTRY.get_sample_value("app_security_events_total", {"event": event}) or 0.0


def test_failed_logins_and_blocked_access_are_counted(client):
    register(client, "watched@example.com")
    before_login, before_denied = _count("login_failed"), _count("access_denied")
    client.cookies.clear()
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json={"email": "watched@example.com", "password": "wrong-password1"}).status_code == 401
    assert _count("login_failed") - before_login == 3
    h = {"Authorization": f"Bearer {register(client, 'nosy@example.com')['access_token']}"}
    assert client.get("/api/v1/platform/stats", headers=h).status_code == 403
    assert _count("access_denied") - before_denied >= 1


def test_metric_labels_hold_no_personal_data():
    labels = {s.labels.get("event") for m in REGISTRY.collect() if m.name == "app_security_events" for s in m.samples}
    assert all(label and "@" not in label and not any(ch.isdigit() for ch in label) for label in labels if label)


def test_sample_data_refuses_to_run_outside_development(monkeypatch):
    from app.ops import seed_demo

    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(SystemExit, match="only for development"):
        seed_demo.run()
