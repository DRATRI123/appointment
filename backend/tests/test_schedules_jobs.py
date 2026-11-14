"""Schedule management rules and the background job wrappers."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.time import utcnow
from app.models import BookingHold
from app.workers import jobs
from app.workers.queue import get_job, get_queue
from tests.booking_helpers import Clinic, iso, ist


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_schedule_exceptions_holidays_and_leaves_management(client):
    c = Clinic(client, email="sched-owner@example.com", name="Schedule Clinic")
    other = Clinic(client, email="sched-other@example.com", name="Other Schedule Clinic")
    day = c.monday

    # A schedule can only be set for a branch the professional works at.
    second_branch = c.post("/branches", {"name": "Annex", "code": "ANX"})
    r = client.put("/api/v1/schedules", json={"professional_id": c.pro["id"], "branch_id": second_branch["id"], "windows": []}, headers=c.h)
    assert r.status_code == 409 and r.json()["code"] == "not_assigned"
    assert [s["weekday"] for s in c.get("/schedules", {"professional_id": c.pro["id"], "branch_id": c.branch["id"]})] == [0, 1, 2, 3, 4]

    # Exceptions: list by range, other tenants cannot delete them.
    exc = c.post("/schedules/exceptions", {"professional_id": c.pro["id"], "branch_id": c.branch["id"], "date": day.isoformat(), "is_available": False, "reason": "Training"})
    assert [e["id"] for e in c.get("/schedules/exceptions", {"professional_id": c.pro["id"], "from_date": day.isoformat(), "to_date": day.isoformat()})] == [exc["id"]]
    assert c.get("/schedules/exceptions", {"from_date": (day + timedelta(days=1)).isoformat()}) == []
    assert client.delete(f"/api/v1/schedules/exceptions/{exc['id']}", headers=other.h).status_code == 404
    assert client.delete(f"/api/v1/schedules/exceptions/{exc['id']}", headers=c.h).status_code == 200
    assert c.get("/schedules/exceptions") == []

    # Holidays: duplicates refused, recurring ones always listed, tenant-scoped deletes.
    hol = c.post("/schedules/holidays", {"date": day.isoformat(), "name": "Festival"})
    assert client.post("/api/v1/schedules/holidays", json={"date": day.isoformat(), "name": "Again"}, headers=c.h).json()["code"] == "holiday_exists"
    c.post("/schedules/holidays", {"date": "2020-01-26", "name": "Republic Day", "is_recurring_yearly": True})
    names = {h["name"] for h in c.get("/schedules/holidays", {"from_date": day.isoformat(), "to_date": day.isoformat()})}
    assert names == {"Festival", "Republic Day"}
    assert client.delete(f"/api/v1/schedules/holidays/{hol['id']}", headers=other.h).status_code == 404
    assert client.delete(f"/api/v1/schedules/holidays/{hol['id']}", headers=c.h).status_code == 200

    # Leaves: invalid ranges refused, updates re-validated, approval recorded, tenant-scoped.
    bad = client.post("/api/v1/schedules/leaves", json={"professional_id": c.pro["id"], "start_at": iso(ist(day, 11)), "end_at": iso(ist(day, 10))}, headers=c.h)
    assert bad.status_code == 422
    leave = c.post("/schedules/leaves", {"professional_id": c.pro["id"], "start_at": iso(ist(day, 9)), "end_at": iso(ist(day, 10)), "reason": "Conference"})
    assert leave["status"] == "approved"
    r = client.patch(f"/api/v1/schedules/leaves/{leave['id']}", json={"end_at": iso(ist(day, 8))}, headers=c.h)
    assert r.status_code == 409
    r = client.patch(f"/api/v1/schedules/leaves/{leave['id']}", json={"end_at": iso(ist(day, 11)), "status": "approved"}, headers=c.h)
    assert r.status_code == 200 and _dt(r.json()["end_at"]) == ist(day, 11)
    listed = c.get("/schedules/leaves", {"professional_id": c.pro["id"], "from_at": iso(ist(day, 0)), "to_at": iso(ist(day, 23))})
    assert [lv["id"] for lv in listed] == [leave["id"]]
    assert c.get("/schedules/leaves", {"to_at": iso(ist(day - timedelta(days=7), 0))}) == []
    # The leave now covers 09:00-11:00, so the first bookable slot is 11:00.
    assert _dt(c.slot_starts(day)[0]) == ist(day, 11)
    assert client.patch(f"/api/v1/schedules/leaves/{leave['id']}", json={"reason": "x"}, headers=other.h).status_code == 404
    assert client.delete(f"/api/v1/schedules/leaves/{leave['id']}", headers=other.h).status_code == 404
    assert client.delete(f"/api/v1/schedules/leaves/{leave['id']}", headers=c.h).status_code == 200
    assert client.delete(f"/api/v1/schedules/leaves/{leave['id']}", headers=c.h).status_code == 404


@pytest.fixture()
def jobs_on_test_db(db, monkeypatch):
    """Jobs open their own session in production; point them at the test transaction instead."""

    @contextmanager
    def _scope():
        # The jobs commit per batch; the test session joins the outer test transaction, which is rolled back at teardown.
        yield db

    monkeypatch.setattr(jobs, "session_scope", _scope)
    return db


def test_every_periodic_job_is_registered_and_runs(jobs_on_test_db, client):
    db = jobs_on_test_db
    c = Clinic(client, email="jobs-owner@example.com", name="Jobs Clinic", payment_mode="pay_at_clinic")
    hold = c.public_hold(ist(c.monday, 9), session_key="job-hold")
    db.execute(update(BookingHold).where(BookingHold.public_id == hold["id"]).values(expires_at=utcnow() - timedelta(minutes=1)))
    assert all(get_job(name) for name in jobs.PERIODIC_JOBS)
    results = {name: get_job(name)() for name in jobs.PERIODIC_JOBS}
    assert results["expire_holds"] == 1
    assert isinstance(results["expire_unpaid_appointments"], int)
    assert isinstance(results["purge_expired_documents"], int)
    assert isinstance(results["schedule_reminders"], int)
    assert isinstance(results["pull_calendar_busy"], int)
    for name in ("dispatch_notifications", "sync_external", "deliver_webhooks"):
        assert isinstance(results[name], dict), name
    # Running again is safe: nothing is expired twice.
    assert get_job("expire_holds")() == 0
    # The inline queue runs a job immediately and reports which one ran.
    assert get_queue().enqueue("expire_holds") == "inline:expire_holds"
    with pytest.raises(LookupError):
        get_job("no_such_job")
