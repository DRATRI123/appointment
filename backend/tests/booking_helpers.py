"""Fixtures for booking tests: an organization with one branch, one service and one scheduled professional."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.helpers import bearer, create_org, register

IST = ZoneInfo("Asia/Kolkata")


def next_weekday(weekday: int, days_ahead_min: int = 3) -> date:
    d = date.today() + timedelta(days=days_ahead_min)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def ist(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST)


def iso(dt: datetime) -> str:
    """ISO 8601 as the API renders it (UTC as 'Z')."""
    return dt.isoformat().replace("+00:00", "Z")


def utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


class Clinic:
    def __init__(self, client, email="clinic-owner@example.com", name="Booking Clinic", payment_mode="full_advance", price=50000, duration=30,
                 verify_mobile=False):
        self.client = client
        self.tokens = register(client, email, "Clinic Owner")
        client.cookies.clear()
        self.org = create_org(client, bearer(self.tokens), name)
        self.h = {**bearer(self.tokens), "X-Organization-Id": self.org["id"]}
        self.branch = self.post("/branches", {"name": "Main", "code": "MAIN"})
        self.service = self.post("/services", {"name": "Consultation", "duration_minutes": duration, "price_paise": price, "payment_mode": payment_mode})
        self.pro = self.post("/professionals", {
            "display_name": "Dr. Slot", "default_duration_minutes": duration, "buffer_minutes": 0,
            "branches": [{"branch_id": self.branch["id"]}], "services": [{"service_id": self.service["id"]}],
        })
        # Monday to Friday 09:00-12:00 IST
        self.put("/schedules", {"professional_id": self.pro["id"], "branch_id": self.branch["id"],
                                "windows": [{"weekday": wd, "start_time": "09:00:00", "end_time": "12:00:00"} for wd in range(5)]})
        self.monday = next_weekday(0)
        # Most tests are about something else; the mobile-code step has its own tests (test_public_booking.py).
        if not verify_mobile:
            self.put(f"/organizations/{self.org['id']}/settings/booking", {"values": {"require_mobile_verification": False}})

    def post(self, path, body, headers=None, expect=201):
        r = self.client.post(f"/api/v1{path}", json=body, headers=headers or self.h)
        assert r.status_code == expect, f"{path}: {r.status_code} {r.text}"
        return r.json()

    def put(self, path, body, expect=200):
        r = self.client.put(f"/api/v1{path}", json=body, headers=self.h)
        assert r.status_code == expect, f"{path}: {r.status_code} {r.text}"
        return r.json()

    def get(self, path, params=None, headers=None, expect=200):
        r = self.client.get(f"/api/v1{path}", params=params, headers=headers or self.h)
        assert r.status_code == expect, f"{path}: {r.status_code} {r.text}"
        return r.json()

    def availability(self, day: date, professional_id=None, public=False):
        params = {"service_id": self.service["id"], "branch_id": self.branch["id"], "date": day.isoformat()}
        if professional_id:
            params["professional_id"] = professional_id
        if public:
            r = self.client.get(f"/api/v1/public/organizations/{self.org['slug']}/availability", params=params)
            assert r.status_code == 200, r.text
            return r.json()
        return self.get("/availability", params)

    def slot_starts(self, day: date, **kw) -> list[str]:
        data = self.availability(day, **kw)
        return [s["start_at"] for p in data["professionals"] for s in p["slots"]]

    def public_hold(self, start: datetime, session_key="sess-1", expect=201):
        r = self.client.post(f"/api/v1/public/organizations/{self.org['slug']}/holds", json={
            "professional_id": self.pro["id"], "branch_id": self.branch["id"], "service_id": self.service["id"], "start_at": iso(start), "session_key": session_key,
        })
        assert r.status_code == expect, r.text
        return r.json()

    def public_book(self, hold_id, session_key="sess-1", customer=None, expect=201, **extra):
        r = self.client.post(f"/api/v1/public/organizations/{self.org['slug']}/appointments", json={
            "hold_id": hold_id, "session_key": session_key,
            "customer": customer or {"full_name": "Guest Patient", "mobile": "9777777777"}, **extra,
        })
        assert r.status_code == expect, r.text
        return r.json()

    def staff_book(self, start: datetime, customer=None, expect=201, **extra):
        return self.post("/appointments", {
            "professional_id": self.pro["id"], "branch_id": self.branch["id"], "service_id": self.service["id"], "start_at": iso(start),
            "customer": customer or {"full_name": "Walk In", "mobile": "9888888888"}, "source": "reception", **extra,
        }, expect=expect)
