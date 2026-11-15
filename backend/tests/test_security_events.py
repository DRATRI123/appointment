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


def test_sample_data_help_changes_nothing(monkeypatch):
    from app.ops import seed_demo

    called = []
    monkeypatch.setattr(seed_demo, "run", lambda: called.append(1) or "ran")
    with pytest.raises(SystemExit) as exc:
        seed_demo.main(["--help"])
    assert exc.value.code == 0 and called == []


def test_meta_answers_with_and_without_trailing_slash(client):
    """The website's proxy strips the slash; a redirect would send the browser to the API host (blocked by CSP)."""
    for path in ("/api/v1/meta", "/api/v1/meta/"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200 and r.json()["environment"] == "test", path
