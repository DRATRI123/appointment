"""Real concurrent requests through the HTTP API, committing to a real database, on SQLite and on PostgreSQL.

SQLite runs one writer at a time, which hides check-then-act races. PostgreSQL runs transactions in parallel, so
these tests are the proof that the rules hold in production: no double booking, no payment verified twice, no
refund beyond what was paid, no coupon used beyond its limit. Set TEST_DATABASE_URL to a PostgreSQL database to
run the PostgreSQL variant (CI does); a separate "<name>_race" database is created next to it.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import create_app
from app.models import Appointment, Base, Payment, PaymentRefund, PaymentVerificationLog
from app.services.seed import seed_all
from tests.booking_helpers import Clinic, iso, ist
from tests.conftest import TEST_DATABASE_URL, is_postgres
from tests.test_payments import _account, _booked, _submit, _verifier

N = 8  # parallel requests per race

BACKENDS = ["sqlite"] + (["postgresql"] if is_postgres() else [])


def _postgres_race_url() -> str:
    url = make_url(TEST_DATABASE_URL)
    race_db = f"{url.database}_race"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": race_db}).scalar():
            conn.execute(text(f'CREATE DATABASE "{race_db}"'))
    admin.dispose()
    return url.set(database=race_db).render_as_string(hide_password=False)


@pytest.fixture(params=BACKENDS)
def race_app(request, tmp_path) -> Generator[tuple[TestClient, Callable[[], TestClient], sessionmaker], None, None]:
    """An app whose every request uses its own committed session, exactly like production get_db."""
    from app.core.config import Settings
    from app.core.database import build_engine

    url = f"sqlite:///{tmp_path / 'race.db'}" if request.param == "sqlite" else _postgres_race_url()
    engine = build_engine(Settings(_env_file=None, app_env="test", database_url=url, rate_limit_enabled=False))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_all(db)
        db.commit()

    def _real_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
            db.commit()
        except Exception as exc:
            if getattr(exc, "persist_changes", False):
                db.commit()
            else:
                db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _real_db
    clients: list[TestClient] = []

    def new_client() -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    try:
        yield new_client(), new_client, factory
    finally:
        for c in clients:
            c.__exit__(None, None, None)
        engine.dispose()


def race(new_client: Callable[[], TestClient], send: Callable[[TestClient, int], object], n: int = N) -> list:
    """Fire n requests at the same instant, each from its own client (own connection, own transaction)."""
    clients = [new_client() for _ in range(n)]
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def run(i: int) -> None:
        barrier.wait()
        try:
            results[i] = send(clients[i], i)
        except Exception as exc:  # a crash is a result too, and must fail the test visibly
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _codes(results) -> list:
    return [r.status_code if hasattr(r, "status_code") else repr(r) for r in results]


def test_overlapping_bookings_of_different_lengths_never_both_succeed(race_app):
    """09:00-10:00 and 09:30-10:00 overlap without sharing a start time, so the unique index cannot catch it."""
    client, new_client, factory = race_app
    c = Clinic(client, email="race-overlap@example.com", payment_mode="pay_at_clinic", duration=30)
    long = c.post("/services", {"name": "Long therapy", "duration_minutes": 60, "price_paise": 0, "payment_mode": "pay_at_clinic"})
    r = client.patch(f"/api/v1/professionals/{c.pro['id']}", json={"services": [{"service_id": c.service["id"]}, {"service_id": long["id"]}]}, headers=c.h)
    assert r.status_code == 200, r.text

    def send(cl, i):
        service, start = (long["id"], ist(c.monday, 9)) if i % 2 == 0 else (c.service["id"], ist(c.monday, 9, 30))
        return cl.post("/api/v1/appointments", headers=c.h, json={
            "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": service, "start_at": iso(start),
            "customer": {"full_name": f"Racer {i}", "mobile": f"97100000{i:02d}"}, "source": "reception"})

    codes = _codes(race(new_client, send))
    assert codes.count(201) == 1 and all(code in (201, 409) for code in codes), codes
    with factory() as db:
        active = db.scalars(select(Appointment).where(Appointment.status.in_(["confirmed", "pending_payment", "pending_verification"]))).all()
        assert len(active) == 1


def test_parallel_holds_and_staff_bookings_on_one_slot_leave_one_winner(race_app):
    client, new_client, factory = race_app
    c = Clinic(client, email="race-mixed@example.com", payment_mode="pay_at_clinic")
    start = ist(c.monday, 10)

    def send(cl, i):
        if i % 2:
            return cl.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", json={
                "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(start), "session_key": f"k{i}"})
        return cl.post("/api/v1/appointments", headers=c.h, json={
            "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(start),
            "customer": {"full_name": f"Walk {i}", "mobile": f"97200000{i:02d}"}, "source": "reception"})

    codes = _codes(race(new_client, send))
    assert codes.count(201) == 1 and all(code in (201, 409) for code in codes), codes


def test_two_reschedules_into_the_same_free_slot(race_app):
    client, new_client, factory = race_app
    c = Clinic(client, email="race-move@example.com", payment_mode="pay_at_clinic")
    appts = [c.staff_book(ist(c.monday, 9) + timedelta(minutes=30 * i), customer={"full_name": f"Mover {i}", "mobile": f"97300000{i:02d}"}) for i in range(4)]
    target = iso(ist(c.monday, 11))

    def send(cl, i):
        return cl.post(f"/api/v1/appointments/{appts[i]['id']}/reschedule", headers=c.h, json={"start_at": target, "reason": "race"})

    codes = _codes(race(new_client, send, n=4))
    assert codes.count(200) == 1 and all(code in (200, 409) for code in codes), codes
    with factory() as db:
        at_target = db.scalar(select(func.count()).select_from(Appointment).where(
            Appointment.start_at == ist(c.monday, 11), Appointment.status.in_(["confirmed", "pending_payment"])))
        assert at_target == 1


def test_a_payment_verified_by_two_people_at_once_counts_once(race_app):
    client, new_client, factory = race_app
    c = Clinic(client, email="race-verify@example.com", name="Verify Race")
    _account(c)
    appt = _booked(c, hour=9, mobile="9740000001")
    payment = _submit(client, c, appt, utr="812345678901")["payment"]
    staff = [_verifier(client, c, mobile=f"96000002{i:02d}") for i in range(4)]

    def send(cl, i):
        return cl.post(f"/api/v1/admin/payments/{payment['id']}/verify", headers=staff[i],
                       json={"bank_credit_confirmed": True, "verified_amount_paise": 50000})

    codes = _codes(race(new_client, send, n=4))
    assert codes.count(200) == 1 and all(code in (200, 409) for code in codes), codes
    with factory() as db:
        p = db.scalars(select(Payment).where(Payment.public_id == payment["id"])).one()
        a = db.get(Appointment, p.appointment_id)
        assert a.paid_amount_paise == 50000  # not 100000 or more
        logs = db.scalar(select(func.count()).select_from(PaymentVerificationLog).where(
            PaymentVerificationLog.payment_id == p.id, PaymentVerificationLog.action == "verified"))
        assert logs == 1


def test_parallel_refund_requests_never_exceed_what_was_paid(race_app):
    client, new_client, factory = race_app
    c = Clinic(client, email="race-refund@example.com", name="Refund Race")
    _account(c)
    appt = _booked(c, hour=9, mobile="9750000001")
    pid = _submit(client, c, appt, utr="912345678901")["payment"]["id"]
    acc = _verifier(client, c, mobile="9600000301")
    assert client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000}, headers=acc).status_code == 200

    def send(cl, i):  # every request asks for the full amount
        return cl.post("/api/v1/refunds", headers=c.h, json={"payment_id": pid, "amount_paise": 50000, "reason": f"Race {i}"})

    codes = _codes(race(new_client, send))
    assert codes.count(201) == 1 and all(code in (201, 409, 422) for code in codes), codes
    with factory() as db:
        p = db.scalars(select(Payment).where(Payment.public_id == pid)).one()
        total = db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(
            PaymentRefund.payment_id == p.id, PaymentRefund.status.in_(["requested", "approved", "processed"])))
        assert total == 50000


def test_a_coupon_limited_to_two_uses_is_used_at_most_twice(race_app):
    """Bookings for three different professionals, so only the coupon itself can serialise them."""
    client, new_client, factory = race_app
    c = Clinic(client, email="race-coupon@example.com", name="Coupon Race", payment_mode="pay_at_clinic")
    pros = [c.pro["id"]]
    for k in range(2):
        pro = c.post("/professionals", {"display_name": f"Dr. Extra {k}", "default_duration_minutes": 30, "buffer_minutes": 0,
                                        "branches": [{"branch_id": c.branch["id"]}], "services": [{"service_id": c.service["id"]}]})
        c.put("/schedules", {"professional_id": pro["id"], "branch_id": c.branch["id"],
                             "windows": [{"weekday": wd, "start_time": "09:00:00", "end_time": "12:00:00"} for wd in range(5)]})
        pros.append(pro["id"])
    c.post("/coupons", {"code": "FIRST2", "discount_type": "flat", "discount_value": 1000, "max_redemptions": 2})

    def send(cl, i):
        return cl.post("/api/v1/appointments", headers=c.h, json={
            "professional_id": pros[i % 3], "branch_id": c.branch["id"], "service_id": c.service["id"],
            "start_at": iso(ist(c.monday, 9) + timedelta(minutes=30 * (i // 3))),
            "customer": {"full_name": f"Saver {i}", "mobile": f"97600000{i:02d}"}, "source": "reception", "coupon_code": "FIRST2"})

    codes = _codes(race(new_client, send, n=6))
    with factory() as db:
        used = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.coupon_code == "FIRST2"))
    assert used == 2 and codes.count(201) == 2 and all(code in (201, 409, 422) for code in codes), (used, codes)


def test_cancel_clicked_twice_cancels_once(race_app):
    from app.models import AppointmentCancellation

    client, new_client, factory = race_app
    c = Clinic(client, email="race-cancel@example.com", name="Cancel Race", payment_mode="pay_at_clinic")
    appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Twice", "mobile": "9770000001"})

    def send(cl, i):
        return cl.post(f"/api/v1/appointments/{appt['id']}/status", headers=c.h, json={"action": "cancel", "reason": f"click {i}"})

    codes = _codes(race(new_client, send, n=4))
    assert codes.count(200) == 1 and all(code in (200, 409) for code in codes), codes
    with factory() as db:
        a = db.scalars(select(Appointment).where(Appointment.public_id == appt["id"])).one()
        assert db.scalar(select(func.count()).select_from(AppointmentCancellation).where(AppointmentCancellation.appointment_id == a.id)) == 1
