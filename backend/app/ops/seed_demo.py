"""Sample data for trying the app on your own computer: ``python -m app.ops.seed_demo``.

Development and test only: it refuses to run with APP_ENV=staging or production, so sample records can never reach a
real database. Everything it creates is clearly marked:
* the clinic is called "Demo Clinic (sample data)" with web address /demo-clinic,
* its owner is demo-owner@example.test (".test" addresses can never receive email),
* patients are called "Sample Patient 1, 2, ..." with mobile numbers 90000000NN.
It goes through the app's own sign-up and booking steps, so the sample data passes the same checks as real data.
Running it again does nothing if the demo clinic already exists. The owner's password is printed once.
"""
from __future__ import annotations

import secrets
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

SLUG = "demo-clinic"
OWNER = "demo-owner@example.test"


def run() -> str:
    s = get_settings()
    if s.app_env not in ("development", "test"):
        raise SystemExit(f"Refused: sample data is only for development (APP_ENV is {s.app_env}).")
    from fastapi.testclient import TestClient

    from app.core.database import session_scope
    from app.main import create_app
    from app.services.seed import seed_all

    with session_scope() as db:
        seed_all(db)  # roles and permissions, as on every fresh database
    app = create_app()
    with TestClient(app, base_url="http://localhost") as c:
        if c.get(f"/api/v1/public/organizations/{SLUG}").status_code == 200:
            return "The demo clinic already exists. Nothing changed."
        password = "Demo-" + secrets.token_urlsafe(9)
        r = c.post("/api/v1/auth/register", json={"full_name": "Demo Owner (sample)", "email": OWNER, "password": password})
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        org = c.post("/api/v1/organizations", headers=h, json={"name": "Demo Clinic (sample data)", "slug": SLUG}).json()
        h["X-Organization-Id"] = org["id"]

        def post(path, body):
            res = c.post(f"/api/v1{path}", headers=h, json=body)
            res.raise_for_status()
            return res.json()

        branch = post("/branches", {"name": "Main (sample)", "code": "MAIN", "phone": "+91 90000 00000"})
        services = [post("/services", {"name": n, "duration_minutes": d, "price_paise": p, "payment_mode": m})
                    for n, d, p, m in [("Consultation (sample)", 30, 50000, "pay_at_clinic"), ("Follow-up (sample)", 15, 30000, "pay_at_clinic"),
                                       ("Therapy session (sample)", 60, 150000, "full_advance")]]
        doctors = [post("/professionals", {"display_name": n, "qualification": q, "branches": [{"branch_id": branch["id"]}],
                                           "services": [{"service_id": sv["id"]} for sv in services]})
                   for n, q in [("Dr. Sample One", "BAMS"), ("Dr. Sample Two", "BAMS, MD")]]
        for d in doctors:
            c.put("/api/v1/schedules", headers=h, json={"professional_id": d["id"], "branch_id": branch["id"],
                  "windows": [{"weekday": wd, "start_time": "09:00:00", "end_time": "17:00:00"} for wd in range(6)]}).raise_for_status()
        tz = ZoneInfo("Asia/Kolkata")
        day = date.today() + timedelta(days=1)
        for i in range(1, 6):
            start = datetime(day.year, day.month, day.day, 9 + i, 0, tzinfo=tz)
            post("/appointments", {"professional_id": doctors[i % 2]["id"], "branch_id": branch["id"], "service_id": services[0]["id"],
                                   "start_at": start.isoformat(), "source": "reception", "confirm_without_payment": True,
                                   "customer": {"full_name": f"Sample Patient {i}", "mobile": f"90000000{i:02d}"}})
    return (f"Created the demo clinic: http://localhost:3000/{SLUG}\n"
            f"Sign in at http://localhost:3000/login with {OWNER} and password {password}\n"
            "(shown once; everything is marked as sample data and exists only on this computer).")


def main(argv: list[str] | None = None) -> int:
    import argparse

    argparse.ArgumentParser(prog="python -m app.ops.seed_demo", description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)  # --help only describes
    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
