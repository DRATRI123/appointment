"""Parallel sessions race for the same slot. Exactly one must win, on the real SQLite engine
(BEGIN IMMEDIATE + partial unique indexes), never relying on application-level luck."""
from __future__ import annotations

import threading
from datetime import time, timedelta

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import build_engine
from app.core.enums import AppointmentStatus
from app.core.exceptions import AppError, SlotUnavailable
from app.models import (
    Base,
    Branch,
    Organization,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Schedule,
    Service,
)
from app.schemas.appointment import AppointmentCreate, CustomerInput, HoldCreate
from app.services.appointment_service import AppointmentService
from app.services.seed import seed_all
from tests.booking_helpers import ist, next_weekday


@pytest.fixture()
def race_env(tmp_path):
    settings = Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'race.db'}", rate_limit_enabled=False)
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        seed_all(db)
        org = Organization(slug="race", code="RACE", name="Race Clinic")
        db.add(org)
        db.flush()
        branch = Branch(organization_id=org.id, name="Main", code="MAIN", slug="main", is_default=True)
        service = Service(organization_id=org.id, name="Consult", slug="consult", price_paise=0, payment_mode="pay_at_clinic", duration_minutes=30)
        pro = Professional(organization_id=org.id, display_name="Dr. Race", slug="dr-race", default_duration_minutes=30)
        db.add_all([branch, service, pro])
        db.flush()
        db.add(ProfessionalBranch(professional_id=pro.id, branch_id=branch.id))
        db.add(ProfessionalService(professional_id=pro.id, service_id=service.id))
        for wd in range(7):
            db.add(Schedule(organization_id=org.id, professional_id=pro.id, branch_id=branch.id, weekday=wd, start_time=time(9, 0), end_time=time(12, 0)))
        db.commit()
        ids = {"org": org.id, "branch": branch.public_id, "service": service.public_id, "pro": pro.public_id}
    yield engine, Session, ids
    engine.dispose()


def _race(Session, ids, worker, n=8):
    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def run(i: int):
        # Everyone lines up before touching the database: the first statement of a session takes
        # the SQLite write lock (BEGIN IMMEDIATE), so sessions must not be opened ahead of the barrier.
        barrier.wait()
        with Session() as db:
            try:
                org = db.get(Organization, ids["org"])
                worker(AppointmentService(db, org), i)
                db.commit()
                outcome = "ok"
            except SlotUnavailable:
                db.rollback()
                outcome = "slot_unavailable"
            except AppError as exc:
                db.rollback()
                outcome = f"error:{exc.code}"
            except OperationalError as exc:  # lock timeout would be a real bug
                db.rollback()
                outcome = f"operational:{exc.orig}"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_parallel_holds_on_one_slot_yield_exactly_one_winner(race_env):
    engine, Session, ids = race_env
    start = ist(next_weekday(0), 9)

    def worker(svc, i):
        svc.create_hold(HoldCreate(professional_id=ids["pro"], branch_id=ids["branch"], service_id=ids["service"], start_at=start, session_key=f"s{i}"), ignore_notice=True)

    results = _race(Session, ids, worker)
    assert results.count("ok") == 1, results
    assert all(r in ("ok", "slot_unavailable") for r in results), results
    with Session() as db:
        from sqlalchemy import func, select

        from app.models import BookingHold

        assert db.scalar(select(func.count()).select_from(BookingHold).where(BookingHold.status == "active")) == 1


def test_parallel_staff_bookings_on_one_slot_yield_exactly_one_appointment(race_env):
    engine, Session, ids = race_env
    start = ist(next_weekday(0), 10)

    def worker(svc, i):
        svc.create(
            AppointmentCreate(professional_id=ids["pro"], branch_id=ids["branch"], service_id=ids["service"], start_at=start,
                              customer=CustomerInput(full_name=f"Racer {i}", mobile=f"97000000{i:02d}"), source="reception"),
            user=None, staff=True,
        )

    results = _race(Session, ids, worker)
    assert results.count("ok") == 1, results
    with Session() as db:
        from sqlalchemy import func, select

        from app.models import Appointment

        active = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.status.in_([AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING_PAYMENT])))
        assert active == 1


def test_unique_index_is_the_last_line_of_defence(race_env):
    """Bypass the availability check and insert two active appointments for one slot directly: the DB refuses."""
    from sqlalchemy.exc import IntegrityError

    from app.core.ids import new_reference
    from app.models import Appointment, Customer

    engine, Session, ids = race_env
    start = ist(next_weekday(0), 11)
    with Session() as db:
        org = db.get(Organization, ids["org"])
        branch = db.query(Branch).first()
        pro = db.query(Professional).first()
        service = db.query(Service).first()
        cust = Customer(organization_id=org.id, full_name="Direct")
        db.add(cust)
        db.flush()

        def make():
            return Appointment(organization_id=org.id, reference=new_reference("APT", org.code), branch_id=branch.id, professional_id=pro.id, service_id=service.id,
                               customer_id=cust.id, start_at=start, end_at=start + timedelta(minutes=30), timezone="Asia/Kolkata", consultation_mode="in_person",
                               status=AppointmentStatus.CONFIRMED, slot_sequence=0)

        db.add(make())
        db.commit()
        db.add(make())
        with pytest.raises(IntegrityError):
            db.commit()
