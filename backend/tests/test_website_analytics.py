"""Campaign attribution on bookings and cookie-free website analytics."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Appointment
from app.models.analytics import WebsiteDailyStat
from tests.booking_helpers import Clinic, iso, ist


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="wa-owner@example.com", name="Analytics Clinic", payment_mode="pay_at_clinic")


def pub(c):
    return f"/api/v1/public/organizations/{c.org['slug']}"


def _book(client, c, hour, attribution=None, key="wa-session"):
    h = client.post(f"{pub(c)}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"],
                                             "start_at": iso(ist(c.monday, hour)), "session_key": f"{key}-{hour}"}).json()
    r = client.post(f"{pub(c)}/appointments", json={"hold_id": h["id"], "session_key": f"{key}-{hour}", "attribution": attribution,
                                                     "customer": {"full_name": "Visitor", "mobile": f"98123456{hour:02d}"}})
    assert r.status_code == 201, r.text
    return r.json()


def test_events_are_counted_without_personal_data(client, clinic, db):
    for _ in range(3):
        assert client.post(f"{pub(clinic)}/events", json={"metric": "page_view", "key": "home", "source": "instagram"}).status_code == 204
    client.post(f"{pub(clinic)}/events", json={"metric": "page_view", "key": "<script>alert(1)</script>", "source": "evil source!"})
    client.post(f"{pub(clinic)}/events", json={"metric": "book_click", "key": "home"})
    assert client.post(f"{pub(clinic)}/events", json={"metric": "purchase"}).status_code == 422
    rows = {(r.metric, r.key, r.source): r.count for r in db.scalars(select(WebsiteDailyStat))}
    assert rows[("page_view", "home", "instagram")] == 3
    assert rows[("page_view", "other", "direct")] == 1 and rows[("book_click", "home", "direct")] == 1
    assert not {"ip_address", "user_agent", "session_key", "visitor_id"} & set(WebsiteDailyStat.__table__.columns.keys())


def test_bookings_keep_clean_campaign_labels_only(client, clinic, db):
    appt = _book(client, clinic, 9, {"utm_source": "Shopify", "utm_campaign": "diwali-2026", "utm_medium": "<b>x</b>", "price": "1", "entry": "embed"})
    row = db.scalar(select(Appointment).where(Appointment.reference == appt["reference"]))
    assert row.metadata_["attribution"] == {"utm_source": "shopify", "utm_campaign": "diwali-2026", "entry": "embed"}
    assert appt["total_amount_paise"] == 50000  # labels never change anything else


def test_report_combines_traffic_holds_and_bookings(client, clinic):
    for _ in range(4):
        client.post(f"{pub(clinic)}/events", json={"metric": "page_view", "key": "home", "source": "google"})
    client.post(f"{pub(clinic)}/events", json={"metric": "page_view", "key": "our-story"})
    client.post(f"{pub(clinic)}/events", json={"metric": "booking_view", "key": "book"})
    _book(client, clinic, 9, {"utm_source": "google", "utm_campaign": "monsoon", "entry": "website"})
    _book(client, clinic, 10, {"entry": "website"})
    _book(client, clinic, 11, None)  # e.g. through the API: an online booking, but not a website conversion
    clinic.staff_book(ist(clinic.monday, 11, 30))  # reception bookings are not online bookings at all
    r = client.get("/api/v1/website/analytics", headers=clinic.h)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["totals"] == {"page_views": 5, "book_clicks": 0, "booking_views": 1, "holds": 3, "bookings": 3, "website_bookings": 2, "conversion_percent": 40.0}
    assert rep["top_pages"][0] == {"key": "home", "views": 4} and {"source": "google", "views": 4} in rep["traffic_sources"]
    assert {"source": "google", "bookings": 1} in rep["booking_sources"] and {"source": "direct", "bookings": 2} in rep["booking_sources"]
    assert rep["campaigns"] == [{"campaign": "monsoon", "bookings": 1}]
    assert len(rep["daily"]) == 30


def test_analytics_needs_report_permission_and_valid_range(client, clinic):
    from tests.test_payments import _verifier

    rec = _verifier(client, clinic, role="receptionist", mobile="9600000951")
    assert client.get("/api/v1/website/analytics", headers=rec).status_code == 403
    r = client.get("/api/v1/website/analytics", params={"from_date": "2026-01-10", "to_date": "2026-01-01"}, headers=clinic.h)
    assert r.status_code == 422
