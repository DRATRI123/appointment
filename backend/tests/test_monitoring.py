"""Prometheus endpoint, readiness checks, platform system status and Sentry scrubbing."""
from __future__ import annotations

import re
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from app.core import database
from app.core.config import get_settings
from app.core.observability import scrub_event
from app.services import ops_service
from tests.booking_helpers import Clinic
from tests.helpers import bearer, register

TOKEN = "m" * 32


@pytest.fixture()
def ops_db(db, monkeypatch):
    """The scrape-time collector opens its own session; point it at the test transaction."""

    @contextmanager
    def _scope():
        yield db

    monkeypatch.setattr(database, "session_scope", _scope)
    return db


def test_metrics_endpoint_is_off_by_default_and_needs_the_token(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_token", None)
    assert client.get("/metrics").status_code == 404
    monkeypatch.setattr(settings, "metrics_token", TOKEN)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    # The API's own proxy path does not expose it.
    assert client.get("/api/v1/metrics").status_code == 404


def test_metrics_use_route_templates_and_report_operations(client, ops_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_token", TOKEN)
    c = Clinic(client, email="metrics-owner@example.com", name="Metrics Clinic")
    auth = {"Authorization": f"Bearer {TOKEN}"}
    line = re.compile(r'app_http_requests_total\{method="GET",route="/api/v1/branches/\{branch_id\}",status="4xx"\} ([0-9.]+)')

    def not_found_count() -> float:
        m = line.search(client.get("/metrics", headers=auth).text)
        return float(m.group(1)) if m else 0.0

    before = not_found_count()  # the counter is process-wide; other tests may already have hit this route
    client.get(f"/api/v1/branches/{c.branch['id']}", headers=c.h)
    client.get("/api/v1/branches/does-not-exist", headers=c.h)
    assert not_found_count() == before + 1
    ops_service.record_heartbeat(ops_db, interval_seconds=20)
    ops_service.record_job(ops_db, "dispatch_notifications", ok=False, duration_ms=5, error="SMTP down")
    ops_service.record_backup(ops_db, {"ok": True, "file": "backup-x.tar.gz.enc"})

    body = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).text
    assert 'route="/api/v1/branches/{branch_id}"' in body
    assert c.branch["id"] not in body and "does-not-exist" not in body  # no IDs in label values
    assert "app_ops_status_up 1.0" in body
    assert re.search(r"app_worker_heartbeat_age_seconds [0-9.]+", body)
    assert 'app_job_consecutive_failures{job="dispatch_notifications"} 1.0' in body
    assert "app_backup_last_ok 1.0" in body
    assert 'app_backlog{kind="payments_awaiting_verification"}' in body
    assert "metrics-owner@example.com" not in body


def test_metrics_report_database_trouble_instead_of_failing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_token", TOKEN)

    @contextmanager
    def _down():
        raise RuntimeError("database unavailable")
        yield

    monkeypatch.setattr(database, "session_scope", _down)
    r = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and "app_ops_status_up 0.0" in r.text


def test_readiness_reports_pending_migrations_and_unwritable_storage(client, db, monkeypatch, tmp_path):
    assert client.get("/api/v1/health/ready").json()["checks"] == {"database": "ok", "migrations": "ok", "storage": "ok"}
    db.execute(text("UPDATE alembic_version SET version_num = 'old0000'"))
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["migrations"].startswith("pending: database at old0000")

    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x")
    monkeypatch.setattr(get_settings(), "storage_local_path", str(blocked / "uploads"))
    assert client.get("/api/v1/health/ready").json()["checks"]["storage"].startswith("error")


def test_platform_system_status_is_for_platform_admins_only(client, db):
    from app.models import User

    tokens = register(client, "ops-admin@example.com")
    client.cookies.clear()
    assert client.get("/api/v1/platform/system-status", headers=bearer(tokens)).status_code == 403
    db.query(User).filter(User.email == "ops-admin@example.com").update({"is_platform_admin": True})
    db.flush()
    ops_service.record_heartbeat(db, interval_seconds=20)
    r = client.get("/api/v1/platform/system-status", headers=bearer(tokens))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker"]["ok"] is True and body["checks"]["migrations"]["ok"] is True
    assert body["backup"]["ok"] is False and any("backup" in a for a in body["attention"])


def test_sentry_events_are_scrubbed_of_personal_data():
    event = {
        "request": {"url": "https://clinic.example.com/api/v1/auth/login", "data": {"password": "Secret123"},
                    "cookies": {"access_token": "jwt"}, "query_string": "mobile=9812345678",
                    "headers": {"Authorization": "Bearer jwt", "Cookie": "a=b", "X-API-Key": "ak_live_x", "User-Agent": "Firefox"}},
        "user": {"email": "asha@example.com", "ip_address": "203.0.113.9"},
        "exception": {"values": [{"stacktrace": {"frames": [{"function": "verify", "vars": {"utr": "412345678901"}}]}}]},
    }
    out = scrub_event(event)
    text_out = str(out)
    for secret in ("Secret123", "jwt", "9812345678", "ak_live_x", "asha@example.com", "412345678901", "203.0.113.9"):
        assert secret not in text_out
    assert out["request"]["headers"]["User-Agent"] == "Firefox"
