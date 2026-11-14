"""Fill an EMPTY, migrated database with a realistic volume of data for performance testing.

    python scripts/perf/seed_volume.py --database-url postgresql+psycopg://app:pw@127.0.0.1/perf --orgs 5

Per clinic: 2 branches, 6 professionals, 5 services, schedules Mon-Sat 09-13 and 14-18, 4,000 patients, and about a
year of appointments (70% of past slots taken, 40% of the next two months) with payments, status history,
notifications and audit entries. Each clinic gets an owner `owner<N>@perf.example.com` / password `PerfTest-2026!`
for the load test. Never run it against a real clinic's database: it refuses a database that already has
organizations.
"""
from __future__ import annotations

import argparse
import random
import sys
import time as clock
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import create_engine, func, insert, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import (  # noqa: E402
    Appointment,
    AppointmentStatusHistory,
    AuditLog,
    Branch,
    Customer,
    Notification,
    Organization,
    OrganizationMembership,
    Payment,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Role,
    Schedule,
    Service,
    User,
)
from app.security.passwords import hash_password  # noqa: E402
from app.services.seed import seed_all  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
PASSWORD = "PerfTest-2026!"
CHUNK = 5000


def bulk(db: Session, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), CHUNK):
        db.execute(insert(model), rows[i:i + CHUNK])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--orgs", type=int, default=5)
    parser.add_argument("--customers", type=int, default=4000, help="patients per clinic")
    parser.add_argument("--days-back", type=int, default=365)
    parser.add_argument("--days-ahead", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    rnd = random.Random(args.seed)
    engine = create_engine(args.database_url)
    started = clock.monotonic()
    totals: dict[str, int] = {}
    with Session(engine) as db:
        if db.scalar(select(func.count()).select_from(Organization)):
            print("error: this database already has organizations; use an empty, migrated database.", file=sys.stderr)
            return 1
        seed_all(db)
        owner_role = db.scalar(select(Role).where(Role.code == "org_owner", Role.organization_id.is_(None)))
        pw_hash = hash_password(PASSWORD)
        today = datetime.now(IST).date()
        now = datetime.now(UTC)
        for o in range(1, args.orgs + 1):
            owner = User(full_name=f"Owner {o}", email=f"owner{o}@perf.example.com", password_hash=pw_hash, status="active", email_verified_at=now)
            org = Organization(slug=f"perf-clinic-{o}", code=f"PC{o:02d}", name=f"Perf Clinic {o}", timezone="Asia/Kolkata", status="active")
            db.add_all([owner, org])
            db.flush()
            org.owner_user_id = owner.id
            db.add(OrganizationMembership(user_id=owner.id, organization_id=org.id, role_id=owner_role.id, status="active"))
            branches = [Branch(organization_id=org.id, name=f"Branch {b}", code=f"B{b}", slug=f"branch-{b}", is_default=b == 1) for b in (1, 2)]
            services = [Service(organization_id=org.id, name=f"Service {s}", slug=f"service-{s}", duration_minutes=30, price_paise=50000 + 10000 * s,
                                payment_mode="full_advance" if s % 2 else "pay_at_clinic") for s in range(1, 6)]
            pros = [Professional(organization_id=org.id, display_name=f"Dr. Perf {p}", slug=f"dr-perf-{p}", default_duration_minutes=30) for p in range(1, 7)]
            db.add_all(branches + services + pros)
            db.flush()
            for i, pro in enumerate(pros):
                branch = branches[i % 2]
                db.add(ProfessionalBranch(professional_id=pro.id, branch_id=branch.id))
                for svc in services:
                    db.add(ProfessionalService(professional_id=pro.id, service_id=svc.id))
                for wd in range(6):
                    for start, end in ((time(9), time(13)), (time(14), time(18))):
                        db.add(Schedule(organization_id=org.id, professional_id=pro.id, branch_id=branch.id, weekday=wd, start_time=start, end_time=end))
            db.flush()

            customers = [{"organization_id": org.id, "full_name": f"Patient {o}-{c}", "mobile": f"+9198{o:02d}{c:06d}",
                          "customer_code": f"PC{o:02d}-{c:05d}", "source": "online", "is_guest": c % 3 == 0} for c in range(args.customers)]
            bulk(db, Customer, customers)
            cust_ids = list(db.scalars(select(Customer.id).where(Customer.organization_id == org.id)))

            appts, seq = [], 0
            for d in range(-args.days_back, args.days_ahead + 1):
                day = today + timedelta(days=d)
                if day.weekday() == 6:
                    continue
                fill = 0.7 if d < 0 else 0.4
                for i, pro in enumerate(pros):
                    for minutes in list(range(9 * 60, 13 * 60, 30)) + list(range(14 * 60, 18 * 60, 30)):
                        if rnd.random() > fill:
                            continue
                        start = datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=IST).astimezone(UTC)
                        svc = services[rnd.randrange(5)]
                        if d < 0:
                            status = rnd.choices(["completed", "cancelled", "no_show"], [85, 10, 5])[0]
                        else:
                            status = "confirmed" if svc.payment_mode == "pay_at_clinic" or rnd.random() < 0.8 else "pending_verification"
                        seq += 1
                        appts.append({"organization_id": org.id, "reference": f"APT-PC{o:02d}-{seq:07d}", "branch_id": branches[i % 2].id, "professional_id": pro.id,
                                      "service_id": svc.id, "customer_id": rnd.choice(cust_ids), "start_at": start, "end_at": start + timedelta(minutes=30),
                                      "timezone": "Asia/Kolkata", "consultation_mode": "in_person", "status": status, "source": rnd.choice(["online", "reception"]),
                                      "subtotal_paise": svc.price_paise, "total_amount_paise": svc.price_paise,
                                      "advance_due_paise": svc.price_paise if svc.payment_mode == "full_advance" else 0,
                                      "paid_amount_paise": svc.price_paise if svc.payment_mode == "full_advance" and status in ("completed", "confirmed") else 0,
                                      "slot_sequence": 0, "created_at": start - timedelta(days=rnd.randint(1, 14))})
            bulk(db, Appointment, appts)
            rows = db.execute(select(Appointment.id, Appointment.status, Appointment.customer_id, Appointment.total_amount_paise, Appointment.advance_due_paise,
                                     Appointment.start_at, Appointment.reference).where(Appointment.organization_id == org.id)).all()
            payments, history, notes, audits = [], [], [], []
            for n, (aid, status, cid, total, advance, start, ref) in enumerate(rows):
                history.append({"appointment_id": aid, "from_status": None, "to_status": "confirmed", "changed_at": start - timedelta(days=2)})
                if status != "confirmed":
                    history.append({"appointment_id": aid, "from_status": "confirmed", "to_status": status, "changed_at": start})
                if advance:
                    pst = "under_review" if status == "pending_verification" else ("verified" if status in ("completed", "confirmed") else "cancelled")
                    payments.append({"organization_id": org.id, "reference": f"PAY-PC{o:02d}-{n:07d}", "appointment_id": aid, "customer_id": cid,
                                     "branch_id": branches[0].id, "amount_paise": advance, "status": pst, "kind": "advance", "method": "upi_qr",
                                     "verified_amount_paise": advance if pst == "verified" else None, "created_at": start - timedelta(days=3)})
                for event in ("appointment.confirmed", "appointment.reminder"):
                    notes.append({"organization_id": org.id, "event": event, "channel": "sms", "recipient_customer_id": cid, "appointment_id": aid,
                                  "recipient_address": "+919800000000", "body": f"Your appointment {ref}", "status": "sent" if start < now else "scheduled",
                                  "scheduled_for": start - timedelta(days=1), "created_at": start - timedelta(days=2)})
                audits.append({"organization_id": org.id, "action": "appointment.created", "entity_type": "appointment", "entity_id": ref,
                               "actor_user_id": owner.id, "created_at": start - timedelta(days=2)})
            bulk(db, Payment, payments)
            bulk(db, AppointmentStatusHistory, history)
            bulk(db, Notification, notes)
            bulk(db, AuditLog, audits)
            db.commit()
            for k, v in (("customers", len(customers)), ("appointments", len(rows)), ("payments", len(payments)), ("notifications", len(notes)),
                         ("status_history", len(history)), ("audit_logs", len(audits))):
                totals[k] = totals.get(k, 0) + v
            print(f"clinic {o}: {len(rows):,} appointments, {len(payments):,} payments", flush=True)
    engine.dispose()
    print("Seeded " + ", ".join(f"{v:,} {k}" for k, v in totals.items()) + f" in {clock.monotonic() - started:.0f}s.")
    print(f"Log in as owner1@perf.example.com / {PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
