from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models import BookingHold
from app.services.appointment_service import expire_unpaid_appointments
from tests.booking_helpers import Clinic, iso, ist, utc
from tests.helpers import bearer, otp_login


def test_availability_follows_schedule_holidays_leaves_and_exceptions(client):
    c = Clinic(client)
    monday = c.monday
    starts = c.slot_starts(monday)
    assert len(starts) == 6  # 09:00..11:30 every 30 minutes
    assert starts[0] == iso(utc(ist(monday, 9))) and starts[-1] == iso(utc(ist(monday, 11, 30)))
    # Public availability is identical.
    assert c.slot_starts(monday, public=True) == starts
    sunday = monday + timedelta(days=6)
    assert c.slot_starts(sunday) == []

    # Holiday blocks the whole day; an available exception opens a Sunday.
    c.post("/schedules/holidays", {"date": monday.isoformat(), "name": "Festival"})
    assert c.slot_starts(monday) == []
    c.post("/schedules/exceptions", {"professional_id": c.pro["id"], "date": sunday.isoformat(), "is_available": True, "start_time": "10:00:00", "end_time": "11:00:00"})
    assert c.slot_starts(sunday) == [iso(utc(ist(sunday, 10))), iso(utc(ist(sunday, 10, 30)))]

    # Leave removes the overlapping part of a day.
    tuesday = monday + timedelta(days=1)
    c.post("/schedules/leaves", {"professional_id": c.pro["id"], "start_at": iso(ist(tuesday, 9)), "end_at": iso(ist(tuesday, 10, 30)), "reason": "Conference"})
    assert c.slot_starts(tuesday) == [iso(utc(ist(tuesday, 10, 30))), iso(utc(ist(tuesday, 11))), iso(utc(ist(tuesday, 11, 30)))]

    # Summary marks days with any slot.
    summary = c.get("/availability/summary", {"service_id": c.service["id"], "branch_id": c.branch["id"], "from_date": monday.isoformat(), "to_date": (monday + timedelta(days=6)).isoformat()})
    by_date = {row["date"]: row["available"] for row in summary}
    assert by_date[monday.isoformat()] is False and by_date[tuesday.isoformat()] is True and by_date[sunday.isoformat()] is True
    assert c.get("/availability/summary", {"service_id": c.service["id"], "branch_id": c.branch["id"], "from_date": monday.isoformat(), "to_date": (monday + timedelta(days=60)).isoformat()}, expect=422)


def test_schedule_requires_branch_assignment_and_rejects_overlaps(client):
    c = Clinic(client)
    other = c.post("/branches", {"name": "Other", "code": "OTH"})
    r = client.put("/api/v1/schedules", json={"professional_id": c.pro["id"], "branch_id": other["id"], "windows": [{"weekday": 0, "start_time": "09:00:00", "end_time": "10:00:00"}]}, headers=c.h)
    assert r.status_code == 409 and r.json()["code"] == "not_assigned"
    r = client.put("/api/v1/schedules", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "windows": [
        {"weekday": 0, "start_time": "09:00:00", "end_time": "11:00:00"}, {"weekday": 0, "start_time": "10:00:00", "end_time": "12:00:00"}]}, headers=c.h)
    assert r.status_code == 422


def test_public_hold_and_booking_flow(client):
    c = Clinic(client)
    start = ist(c.monday, 9, 30)
    hold = c.public_hold(start)
    assert hold["status"] == "active"
    # The held slot disappears for everyone; a second hold on it is refused.
    assert iso(utc(start)) not in c.slot_starts(c.monday, public=True)
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(start), "session_key": "other"})
    assert r.status_code == 409 and r.json()["code"] == "slot_unavailable"
    # Another session cannot book my hold.
    c.public_book(hold["id"], session_key="someone-else", expect=403)
    # Booking without a hold is refused for the public.
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(start), "customer": {"full_name": "Xavier", "mobile": "9000000000"}})
    assert r.status_code == 422 and r.json()["code"] == "hold_required", r.text

    quote = client.get(f"/api/v1/public/organizations/{c.org['slug']}/quote", params={"service_id": c.service["id"], "branch_id": c.branch["id"]}).json()
    assert quote["total_amount_paise"] == 50000 and quote["advance_due_paise"] == 50000

    appt = c.public_book(hold["id"], customer_notes="First visit")
    assert appt["status"] == "pending_payment" and appt["advance_due_paise"] == 50000 and appt["payment_due_at"]
    assert appt["reference"].startswith("APT-") and appt["access_token"]
    assert appt["customer"]["mobile"] == "+919777777777" and appt["customer"]["is_guest"] is True
    assert appt["history"][0]["to_status"] == "pending_payment"
    # Hold is consumed; slot stays blocked by the appointment.
    assert iso(utc(start)) not in c.slot_starts(c.monday)
    c.public_book(hold["id"], expect=409)

    # Status page needs the access token (or the owning user).
    ref = appt["reference"]
    assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{ref}").status_code == 403
    r = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{ref}", params={"access_token": appt["access_token"]})
    assert r.status_code == 200 and r.json()["can_cancel"] is True and r.json()["access_token"] is None
    # Guest cancels online with the token; slot frees up.
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{ref}/cancel", params={"access_token": appt["access_token"]}, json={"action": "cancel", "reason": "Plans changed"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert iso(utc(start)) in c.slot_starts(c.monday)


def test_guest_booking_can_be_disabled(client):
    c = Clinic(client)
    c.put(f"/organizations/{c.org['id']}/settings/booking", {"values": {"allow_guest_booking": False}})
    hold = c.public_hold(ist(c.monday, 9))
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "sess-1", "customer": {"full_name": "Guest", "mobile": "9111111112"}})
    assert r.status_code == 422 and r.json()["code"] == "login_required"
    # A signed-in customer can still book; the appointment is linked to their account.
    user = otp_login(client, "9111111112", "Asha")
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "sess-1", "customer": {"full_name": "Asha"}}, headers=bearer(user))
    assert r.status_code == 201, r.text
    client.cookies.clear()
    mine = client.get("/api/v1/customer/appointments", headers=bearer(user)).json()
    assert len(mine) == 1 and mine[0]["organization_slug"] == c.org["slug"] and mine[0]["customer"]["is_guest"] is False


def test_expired_hold_frees_slot_and_cannot_be_booked(client, db):
    c = Clinic(client)
    start = ist(c.monday, 10)
    hold = c.public_hold(start)
    row = db.scalar(select(BookingHold).where(BookingHold.public_id == hold["id"]))
    row.expires_at = row.expires_at - timedelta(hours=1)
    db.flush()
    assert iso(utc(start)) in c.slot_starts(c.monday)
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "sess-1", "customer": {"full_name": "Late", "mobile": "9222222223"}})
    assert r.status_code == 409 and r.json()["code"] == "hold_expired"


def test_staff_booking_pricing_and_lifecycle(client):
    c = Clinic(client)
    r = client.patch(f"/api/v1/services/{c.service['id']}", json={"payment_mode": "partial_advance", "advance_amount_paise": 20000, "tax_percent": 10, "discounted_price_paise": 40000}, headers=c.h)
    assert r.status_code == 200, r.text
    start = ist(c.monday, 11)
    appt = c.staff_book(start)
    assert appt["subtotal_paise"] == 50000 and appt["discount_paise"] == 10000 and appt["tax_paise"] == 4000
    assert appt["total_amount_paise"] == 44000 and appt["advance_due_paise"] == 20000
    assert appt["status"] == "pending_payment" and appt["source"] == "reception"
    assert appt["pricing_snapshot"]["price_source"] == "service"

    # Same slot again is refused even for staff.
    c.staff_book(start, expect=409)
    # Professional fee override changes the price.
    client.patch(f"/api/v1/professionals/{c.pro['id']}", json={"services": [{"service_id": c.service["id"], "fee_override_paise": 60000}]}, headers=c.h)
    appt2 = c.staff_book(ist(c.monday, 9), confirm_without_payment=True)
    assert appt2["subtotal_paise"] == 60000 and appt2["pricing_snapshot"]["price_source"] == "professional"
    assert appt2["status"] == "confirmed" and appt2["payment_due_at"] is None

    aid = appt2["id"]
    for action, expected in (("check_in", "checked_in"), ("start", "in_progress"), ("complete", "completed")):
        r = client.post(f"/api/v1/appointments/{aid}/status", json={"action": action}, headers=c.h)
        assert r.status_code == 200 and r.json()["status"] == expected, r.text
    r = client.post(f"/api/v1/appointments/{aid}/status", json={"action": "cancel"}, headers=c.h)
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"
    detail = c.get(f"/appointments/{aid}")
    assert [h["to_status"] for h in detail["history"]] == ["confirmed", "checked_in", "in_progress", "completed"]

    # Staff cancel of the pending one releases the slot; a no-show is recorded on a confirmed one.
    r = client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel", "reason": "Patient called"}, headers=c.h)
    assert r.json()["status"] == "cancelled"
    assert iso(utc(start)) in c.slot_starts(c.monday)

    # Calendar + list filters.
    events = c.get("/appointments/calendar", {"from_at": iso(ist(c.monday, 0)), "to_at": iso(ist(c.monday, 23, 59))})
    assert {e["status"] for e in events} == {"completed", "cancelled"}
    assert len(c.get("/appointments", {"status": "completed"})) == 1
    assert len(c.get("/appointments", {"search": "walk"})) == 2


def test_reschedule_rules_for_staff_and_customers(client):
    c = Clinic(client, payment_mode="pay_at_clinic")
    user = otp_login(client, "9333333334", "Ravi")
    client.cookies.clear()
    hold = c.public_hold(ist(c.monday, 9))
    appt = c.public_book(hold["id"], customer={"full_name": "Ravi"}, expect=201) if False else None
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "sess-1", "customer": {"full_name": "Ravi"}}, headers=bearer(user))
    appt = r.json()
    assert appt["status"] == "confirmed"  # pay at clinic → nothing due now

    # Customer must reschedule via a new hold.
    r = client.post(f"/api/v1/customer/appointments/{appt['id']}/reschedule", json={"start_at": iso(ist(c.monday, 10))}, headers=bearer(user))
    assert r.status_code == 422 and r.json()["code"] == "hold_required", r.text
    new_hold = client.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 10)), "session_key": "s2"}, headers=bearer(user)).json()
    r = client.post(f"/api/v1/customer/appointments/{appt['id']}/reschedule", json={"hold_id": new_hold["id"], "reason": "Traffic"}, headers=bearer(user))
    assert r.status_code == 200, r.text
    assert r.json()["start_at"] == iso(utc(ist(c.monday, 10)))
    assert iso(utc(ist(c.monday, 9))) in c.slot_starts(c.monday)

    # max_reschedules = 1 now blocks the customer but not staff.
    c.put(f"/organizations/{c.org['id']}/settings/cancellation", {"values": {"max_reschedules": 1}})
    mine = client.get(f"/api/v1/customer/appointments/{appt['id']}", headers=bearer(user)).json()
    assert mine["can_reschedule"] is False and mine["can_cancel"] is True
    r = client.post(f"/api/v1/appointments/{appt['id']}/reschedule", json={"start_at": iso(ist(c.monday, 11))}, headers=c.h)
    assert r.status_code == 200 and r.json()["start_at"] == iso(utc(ist(c.monday, 11)))

    # Cancellation window: 24 hours before → appointment 3+ days out is fine; set a huge window to close it.
    c.put(f"/organizations/{c.org['id']}/settings/cancellation", {"values": {"cancel_before_hours": 24 * 30}})
    r = client.post(f"/api/v1/customer/appointments/{appt['id']}/cancel", json={"action": "cancel"}, headers=bearer(user))
    assert r.status_code == 403 and r.json()["code"] == "cancel_window_closed"
    c.put(f"/organizations/{c.org['id']}/settings/cancellation", {"values": {"cancel_before_hours": 2}})
    r = client.post(f"/api/v1/customer/appointments/{appt['id']}/cancel", json={"action": "cancel"}, headers=bearer(user))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_recurring_series_skips_blocked_dates(client):
    c = Clinic(client, payment_mode="pay_at_clinic")
    second = c.monday + timedelta(days=7)
    c.post("/schedules/leaves", {"professional_id": c.pro["id"], "start_at": iso(ist(second, 0)), "end_at": iso(ist(second, 23, 59))})
    r = client.post("/api/v1/appointments/recurring", json={
        "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 9)),
        "customer": {"full_name": "Weekly Patient", "mobile": "9444444445"}, "source": "reception", "occurrences": 4, "interval_days": 7,
    }, headers=c.h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["created"]) == 3 and len(body["skipped"]) == 1
    assert body["skipped"][0]["start_at"].startswith(second.isoformat())
    assert all(a["recurrence_group_id"] == body["recurrence_group_id"] for a in body["created"])
    assert body["created"][1]["parent_appointment_id"] == body["created"][0]["id"]


def test_capacity_allows_group_slots(client):
    c = Clinic(client, payment_mode="pay_at_clinic")
    c.put("/schedules", {"professional_id": c.pro["id"], "branch_id": c.branch["id"], "windows": [{"weekday": 0, "start_time": "09:00:00", "end_time": "10:00:00", "capacity": 2}]})
    data = c.availability(c.monday)
    assert data["professionals"][0]["slots"][0]["remaining"] == 2
    c.staff_book(ist(c.monday, 9), customer={"full_name": "Amit", "mobile": "9555555551"})
    assert c.availability(c.monday)["professionals"][0]["slots"][0]["remaining"] == 1
    c.staff_book(ist(c.monday, 9), customer={"full_name": "Bina", "mobile": "9555555552"})
    assert iso(utc(ist(c.monday, 9))) not in c.slot_starts(c.monday)
    c.staff_book(ist(c.monday, 9), customer={"full_name": "Chaya", "mobile": "9555555553"}, expect=409)


def test_waitlist_and_unpaid_expiry_job(client, db):
    c = Clinic(client)
    w = c.post("/waitlist", {"customer": {"full_name": "Waiting", "mobile": "9666666661"}, "professional_id": c.pro["id"], "preferred_date": iso(ist(c.monday, 9))})
    assert w["status"] == "waiting" and len(c.get("/waitlist")) == 1
    assert client.post("/api/v1/waitlist", json={"customer": {"full_name": "Waiting", "mobile": "9666666661"}, "professional_id": c.pro["id"], "preferred_date": iso(ist(c.monday, 9))}, headers=c.h).status_code == 409
    client.delete(f"/api/v1/waitlist/{w['id']}", headers=c.h)
    assert c.get("/waitlist") == []

    appt = c.staff_book(ist(c.monday, 9))
    assert appt["status"] == "pending_payment"
    from app.models import Appointment

    row = db.scalar(select(Appointment).where(Appointment.public_id == appt["id"]))
    row.payment_due_at = row.payment_due_at - timedelta(hours=2)
    db.flush()
    assert expire_unpaid_appointments(db) == 1
    assert c.get(f"/appointments/{appt['id']}")["status"] == "expired"
    assert iso(utc(ist(c.monday, 9))) in c.slot_starts(c.monday)


def test_professional_sees_only_own_appointments(client):
    c = Clinic(client, payment_mode="pay_at_clinic")
    other = c.post("/professionals", {"display_name": "Dr. Other", "branches": [{"branch_id": c.branch["id"]}], "services": [{"service_id": c.service["id"]}]})
    c.put("/schedules", {"professional_id": other["id"], "branch_id": c.branch["id"], "windows": [{"weekday": 0, "start_time": "09:00:00", "end_time": "12:00:00"}]})
    c.staff_book(ist(c.monday, 9))
    c.post("/appointments", {"professional_id": other["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 9)), "customer": {"full_name": "Other Pt", "mobile": "9777777771"}, "source": "reception"})
    # Link a doctor account to Dr. Slot.
    member = c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9999999991", "full_name": "Dr. Slot", "role_code": "doctor"})
    client.patch(f"/api/v1/professionals/{c.pro['id']}", json={"user_id": member["user"]["id"]}, headers=c.h)
    doc = otp_login(client, "9999999991")
    client.cookies.clear()
    hd = {**bearer(doc), "X-Organization-Id": c.org["id"]}
    mine = client.get("/api/v1/appointments", headers=hd).json()
    assert len(mine) == 1 and mine[0]["professional_id"] == c.pro["id"]
    other_appt = [a for a in c.get("/appointments") if a["professional_id"] == other["id"]][0]
    assert client.get(f"/api/v1/appointments/{other_appt['id']}", headers=hd).status_code == 403
    assert client.post(f"/api/v1/appointments/{mine[0]['id']}/status", json={"action": "check_in"}, headers=hd).status_code == 200
    # Doctors may manage their own appointments but never someone else's.
    assert client.post(f"/api/v1/appointments/{other_appt['id']}/status", json={"action": "check_in"}, headers=hd).status_code == 403
    # Plain staff (read only) cannot change status at all.
    staff = c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9999999992", "full_name": "Helper", "role_code": "staff"})
    assert staff["role_code"] == "staff"
    helper = otp_login(client, "9999999992")
    client.cookies.clear()
    hs = {**bearer(helper), "X-Organization-Id": c.org["id"]}
    assert client.get("/api/v1/appointments", headers=hs).status_code == 200
    assert client.post(f"/api/v1/appointments/{mine[0]['id']}/status", json={"action": "complete"}, headers=hs).status_code == 403
