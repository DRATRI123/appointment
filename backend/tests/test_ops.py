"""Worker bookkeeping and the operational status summary."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.services import ops_service
from app.workers import jobs, queue, runner


@pytest.fixture()
def worker_db(db, monkeypatch):
    @contextmanager
    def _scope():
        yield db

    monkeypatch.setattr(jobs, "session_scope", _scope)
    monkeypatch.setattr(runner, "session_scope", _scope)
    return db


def test_worker_cycle_records_heartbeat_and_each_job(worker_db):
    r = runner.Runner(interval=20)
    outcome = r.run_cycle()
    assert set(outcome) == set(jobs.PERIODIC_JOBS) and all(outcome.values())
    status = ops_service.system_status(worker_db)
    assert status["worker"]["ok"] is True and status["worker"]["interval_seconds"] == 20
    for name in jobs.PERIODIC_JOBS:
        job = status["jobs"][name]
        assert job["last_success_at"] and job["runs"] == 1 and job["consecutive_failures"] == 0


def test_a_failing_job_is_recorded_and_does_not_stop_the_others(worker_db, monkeypatch):
    def boom():
        raise RuntimeError("SMTP server unreachable")

    monkeypatch.setitem(queue._REGISTRY, "dispatch_notifications", boom)
    r = runner.Runner()
    for _ in range(3):
        outcome = r.run_cycle()
    assert outcome["dispatch_notifications"] is False
    assert all(ok for name, ok in outcome.items() if name != "dispatch_notifications")
    status = ops_service.system_status(worker_db)
    job = status["jobs"]["dispatch_notifications"]
    assert job["consecutive_failures"] == 3 and job["failures"] == 3 and "SMTP server unreachable" in job["last_error"]
    assert status["status"] == "attention" and any("dispatch_notifications" in a for a in status["attention"])

    monkeypatch.setitem(queue._REGISTRY, "dispatch_notifications", lambda: {"sent": 0})
    r.run_cycle()
    job = ops_service.system_status(worker_db)["jobs"]["dispatch_notifications"]
    assert job["consecutive_failures"] == 0 and job["last_error"] is None and job["failures"] == 3


def test_stop_request_finishes_the_current_job_then_exits(worker_db, monkeypatch):
    r = runner.Runner(interval=3600)
    seen = []

    def first():
        seen.append("first")
        r.stop()  # SIGTERM arrives while this job runs
        return 0

    monkeypatch.setattr(jobs, "PERIODIC_JOBS", ("first", "second"))
    monkeypatch.setitem(queue._REGISTRY, "first", first)
    monkeypatch.setitem(queue._REGISTRY, "second", lambda: seen.append("second"))
    r.forever()  # returns instead of sleeping for an hour
    assert seen == ["first"]


def test_once_exit_code_reflects_failures(worker_db, monkeypatch):
    monkeypatch.setattr(jobs, "PERIODIC_JOBS", ("ok_job",))
    monkeypatch.setitem(queue._REGISTRY, "ok_job", lambda: 1)
    assert runner.main(["--once"]) == 0
    monkeypatch.setitem(queue._REGISTRY, "ok_job", lambda: 1 / 0)
    assert runner.main(["--once"]) == 1


def test_status_flags_a_silent_worker_and_a_missing_backup(worker_db):
    status = ops_service.system_status(worker_db)
    assert status["status"] == "attention"
    assert status["worker"]["ok"] is False and status["backup"]["ok"] is False

    ops_service.record_heartbeat(worker_db, interval_seconds=60)
    ops_service.record_backup(worker_db, {"ok": True, "file": "app-20261114.tar.gz", "size_bytes": 1234})
    status = ops_service.system_status(worker_db)
    assert status["worker"]["ok"] and status["backup"]["ok"] and status["status"] == "ok"

    # A heartbeat older than five minutes means the worker is down.
    row = worker_db.scalars(ops_service.select(ops_service.SystemSetting).where(ops_service.SystemSetting.key == ops_service.HEARTBEAT_KEY)).one()
    row.value = {**row.value, "at": (utcnow() - timedelta(minutes=6)).isoformat()}
    worker_db.flush()
    assert ops_service.system_status(worker_db)["worker"]["ok"] is False
    # A failed backup run is not a successful backup.
    ops_service.record_backup(worker_db, {"ok": False, "error": "disk full"})
    assert ops_service.system_status(worker_db)["backup"]["ok"] is False
