"""N+1 guard: list endpoints must run the same number of queries for 3 rows as for 18.

Measured the way production runs (a fresh session per request, real commits), because the test harness's shared
session would hide the most common cause here: SQLAlchemy's identity map holds objects weakly, so a per-row
db.get() re-queries unless something keeps the loaded rows alive.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import build_engine, get_db
from app.main import create_app
from app.models import Base
from app.services.seed import seed_all
from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, otp_login
from tests.test_payments import _account, _submit, _verifier

ALLOWED_GROWTH = 2  # e.g. one extra page of results; anything per-row is a bug


@pytest.fixture()
def prod_app(tmp_path):
    engine = build_engine(Settings(_env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path / 'q.db'}", rate_limit_enabled=False))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_all(db)
        db.commit()

    def _db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
            db.commit()
        except Exception as exc:
            db.commit() if getattr(exc, "persist_changes", False) else db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _db
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


@contextmanager
def count_queries(engine):
    box = {"n": 0}

    def before(*_a, **_k):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield box
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_list_endpoints_do_not_query_per_row(prod_app):
    client, engine = prod_app
    c = Clinic(client, email="nplus1@example.com", name="Busy Clinic")
    _account(c)
    acc = _verifier(client, c, mobile="9600000501")
    patient = otp_login(client, "9811100000", "Regular Patient")
    client.cookies.clear()
    hp = bearer(patient)
    n = {"made": 0}

    def add(k: int) -> None:
        for _ in range(k):
            i = n["made"]
            n["made"] += 1
            start = ist(c.monday + timedelta(days=7 * (i // 6)), 9) + timedelta(minutes=30 * (i % 6))
            hold = client.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", headers=hp, json={
                "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(start), "session_key": f"q{i}"}).json()
            appt = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", headers=hp, json={
                "hold_id": hold["id"], "session_key": f"q{i}", "customer": {"full_name": f"Patient {i}", "mobile": f"98{i:08d}"}}).json()
            pid = _submit(client, c, appt, utr=f"7{i:011d}")["payment"]["id"]
            if i % 2 == 0:
                client.post(f"/api/v1/admin/payments/{pid}/verify", headers=acc, json={"bank_credit_confirmed": True, "verified_amount_paise": 50000})
                client.post("/api/v1/refunds", headers=c.h, json={"payment_id": pid, "amount_paise": 1000, "reason": "Partial"})
            c.post("/waitlist", {"customer": {"full_name": f"Waiting {i}", "mobile": f"97{i:08d}"}, "professional_id": c.pro["id"],
                                 "preferred_date": iso(start)})

    window = {"from_at": iso(ist(c.monday, 0)), "to_at": iso(ist(c.monday + timedelta(days=60), 0))}
    endpoints = {
        "appointments": ("/api/v1/appointments", window, c.h),
        "calendar": ("/api/v1/appointments/calendar", window, c.h),
        "customers": ("/api/v1/customers", {"page_size": 50}, c.h),
        "payments": ("/api/v1/payments", {"page_size": 50}, c.h),
        "verification queue": ("/api/v1/payments", {"status": "submitted,under_review", "page_size": 50}, c.h),
        "refunds": ("/api/v1/refunds", None, c.h),
        "waitlist": ("/api/v1/waitlist", None, c.h),
        "notifications": ("/api/v1/notifications", {"page_size": 50}, c.h),
        "audit log": (f"/api/v1/organizations/{c.org['id']}/audit-logs", {"page_size": 50}, c.h),
        "dashboard": ("/api/v1/analytics/dashboard", None, c.h),
        "patient's own appointments": ("/api/v1/customer/appointments", None, hp),
    }

    def measure() -> dict[str, int]:
        out = {}
        for name, (path, params, headers) in endpoints.items():
            with count_queries(engine) as box:
                r = client.get(path, params=params, headers=headers)
            assert r.status_code == 200, (name, r.status_code, r.text[:200])
            out[name] = box["n"]
        return out

    add(3)
    small = measure()
    add(15)
    large = measure()
    growth = {name: (small[name], large[name]) for name in endpoints if large[name] - small[name] > ALLOWED_GROWTH}
    assert growth == {}, f"queries grow with rows (3 rows -> 18 rows): {growth}"
