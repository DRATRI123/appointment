"""The worker container's health check: healthy only while cycles keep finishing."""
from __future__ import annotations

from datetime import timedelta

from app.services import ops_service


def test_worker_is_alive_only_after_a_recent_cycle(db, monkeypatch):
    assert ops_service.worker_alive(db, interval_seconds=20) is False  # never ran
    ops_service.record_heartbeat(db, interval_seconds=20)
    assert ops_service.worker_alive(db, interval_seconds=20) is True
    later = ops_service.utcnow() + timedelta(minutes=3)
    monkeypatch.setattr(ops_service, "utcnow", lambda: later)
    assert ops_service.worker_alive(db, interval_seconds=20) is False  # stuck for longer than 2 minutes
