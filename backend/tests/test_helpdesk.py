"""Patient help desk: patients ask, staff answer; privacy, permissions, branches, attachments, notifications, lifecycle."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, text

from app.core.time import utcnow
from app.models import AuditLog, Notification, SupportMessage, SupportTicket
from app.services.helpdesk_service import close_stale
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _patient(client, clinic: Clinic, mobile: str, hour: int = 9, session: str = "hd-1") -> tuple[dict, dict]:
    """A patient who booked as a guest and signed in with a code to that mobile number."""
    hold = clinic.public_hold(ist(clinic.monday, hour), session_key=session)
    client.cookies.clear()
    booking = clinic.public_book(hold["id"], session_key=session, customer={"full_name": f"Patient {mobile[-2:]}", "mobile": mobile})
    client.cookies.clear()
    h = bearer(otp_login(client, mobile))
    client.cookies.clear()
    return h, booking


def _ask(client, clinic, h, expect=201, files=None, **form):
    data = {"category": "payment", "subject": "Paid twice?", "body": "I think I was charged twice for my visit.", **form}
    r = client.post(f"/api/v1/customer/organizations/{clinic.org['id']}/requests", data=data, files=files, headers=h)
    assert r.status_code == expect, r.text
    return r.json()


def test_patient_asks_staff_answer_and_the_conversation_flows(client, db):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    h, booking = _patient(client, clinic, "9822200001")
    base = f"/api/v1/customer/organizations/{clinic.org['id']}/requests"
    assert client.get(f"/api/v1/public/organizations/{clinic.org['slug']}/help").json()["enabled"] is True

    t = _ask(client, clinic, h, appointment_reference=booking["reference"], files={"file": ("receipt.png", PNG, "image/png")})
    assert t["number"] == 1 and t["status"] == "open" and t["appointment"]["reference"] == booking["reference"]
    assert t["messages"][0]["author_kind"] == "customer" and t["messages"][0]["attachment"]["name"] == "receipt.png"
    second = _ask(client, clinic, h, subject="Parking?", category="other")
    assert second["number"] == 2  # numbered per clinic
    # Stored encrypted, never as plain text.
    raw = db.execute(text("SELECT body FROM support_messages ORDER BY id LIMIT 1")).scalar()
    assert "charged twice" not in raw
    # Staff are told (in-app), without the message text.
    staff_note = db.scalar(select(Notification).where(Notification.event == "staff.helpdesk_message"))
    assert staff_note is not None and "charged twice" not in (staff_note.body or "")

    # The inbox.
    summary = clinic.get("/helpdesk/summary")
    assert summary["open"] == 2 and summary["unassigned"] == 2
    inbox = clinic.get("/helpdesk/tickets")
    assert inbox["meta"]["total"] == 2 and inbox["data"][0]["customer"]["name"].startswith("Patient")
    assert clinic.get("/helpdesk/tickets", {"search": "#1"})["meta"]["total"] == 1
    assert clinic.get("/helpdesk/tickets", {"search": "parking"})["data"][0]["number"] == 2

    # Internal note: never shown to the patient. Reply: shown, patient told, first response recorded, assigned to the replier.
    r = client.post(f"/api/v1/helpdesk/tickets/{t['id']}/messages", data={"body": "Check the bank statement first.", "internal": "true"}, headers=clinic.h)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/helpdesk/tickets/{t['id']}/messages", data={"body": "Only one payment reached us; we will check again."}, headers=clinic.h)
    staff_view = r.json()
    assert staff_view["status"] == "pending_customer" and staff_view["first_response_at"] and staff_view["assigned_to"]["name"] == "Clinic Owner"
    assert len(staff_view["messages"]) == 3
    mine = client.get(f"{base}/{t['id']}", headers=h).json()
    assert [m["author_kind"] for m in mine["messages"]] == ["customer", "staff"]
    assert "bank statement" not in str(mine) and mine["messages"][1]["author_name"] == "Clinic"
    reply_note = db.scalar(select(Notification).where(Notification.event == "helpdesk.reply", Notification.channel == "email"))
    assert reply_note is None or "Only one payment" not in reply_note.body  # the answer is read after signing in

    # Attachments: the patient opens their own; staff open it (audit-logged).
    a = client.get(f"{base}/{t['id']}/messages/{t['messages'][0]['id']}/attachment", headers=h)
    assert a.status_code == 200 and a.content == PNG and "no-store" in a.headers["cache-control"]
    assert client.get(f"/api/v1/helpdesk/tickets/{t['id']}/messages/{t['messages'][0]['id']}/attachment", headers=clinic.h).content == PNG
    assert db.scalar(select(AuditLog).where(AuditLog.action == "helpdesk.attachment_opened")) is not None

    # The patient answers: open again; marks it solved with a rating.
    r = client.post(f"{base}/{t['id']}/messages", data={"body": "Thanks, here is my bank SMS."}, headers=h)
    assert r.json()["status"] == "open"
    r = client.post(f"{base}/{t['id']}/resolve", json={"rating": 5}, headers=h)
    assert r.json()["status"] == "resolved" and r.json()["rating"] == 5
    assert clinic.get("/helpdesk/summary")["avg_rating"] == 5.0


def test_patients_only_see_their_own_requests_and_nobody_else_sees_the_inbox(client):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    other = Clinic(client, email="hd-other@example.com", name="Other Clinic", payment_mode="pay_at_clinic")
    h1, _ = _patient(client, clinic, "9822200002")
    h2, _ = _patient(client, clinic, "9822200003", hour=10, session="hd-2")
    t = _ask(client, clinic, h1)
    base = f"/api/v1/customer/organizations/{clinic.org['id']}/requests"
    assert client.get(f"{base}/{t['id']}", headers=h2).status_code == 404
    assert client.get(base, headers=h2).json() == []
    assert client.post(f"{base}/{t['id']}/messages", data={"body": "hi"}, headers=h2).status_code == 404
    # Another clinic's staff: not found. A booking that is not yours: refused.
    assert client.get(f"/api/v1/helpdesk/tickets/{t['id']}", headers=other.h).status_code == 404
    other_booking = other.public_book(other.public_hold(ist(other.monday, 9), session_key="hd-3")["id"], session_key="hd-3")
    client.cookies.clear()
    assert _ask(client, clinic, h1, expect=422, appointment_reference=other_booking["reference"])["code"] == "appointment_not_found"
    # A wrong file type is refused.
    assert _ask(client, clinic, h1, expect=422, files={"file": ("x.exe", b"MZ\x90\x00" * 20, "application/octet-stream")})["code"] == "unsupported_file"


def test_permissions_and_branch_isolation(client, db):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    h, booking = _patient(client, clinic, "9822200004")
    t = _ask(client, clinic, h, appointment_reference=booking["reference"])
    general = _ask(client, clinic, h, subject="Opening hours?", category="other")
    east = clinic.post("/branches", {"name": "East", "code": "EAST"})
    org = clinic.org["id"]
    for mobile, name, role, branch in (("9822200010", "East Desk", "receptionist", east["id"]), ("9822200011", "Doctor", "doctor", None),
                                       ("9822200012", "Front Desk", "receptionist", None)):
        body = {"identifier": mobile, "full_name": name, "role_code": role, **({"branch_id": branch} if branch else {})}
        r = client.post(f"/api/v1/organizations/{org}/members", headers=clinic.h, json=body)
        assert r.status_code == 201, r.text
    east_desk = {**bearer(otp_login(client, "9822200010")), "X-Organization-Id": org}
    doctor = {**bearer(otp_login(client, "9822200011")), "X-Organization-Id": org}
    desk = {**bearer(otp_login(client, "9822200012")), "X-Organization-Id": org}
    client.cookies.clear()
    assert client.get("/api/v1/helpdesk/tickets", headers=doctor).status_code == 403  # no help desk permission
    assert client.get("/api/v1/helpdesk/tickets", headers=desk).json()["meta"]["total"] == 2
    # Staff of the East branch: not the request about a Main-branch booking, but the general one.
    east_view = client.get("/api/v1/helpdesk/tickets", headers=east_desk).json()["data"]
    assert {x["id"] for x in east_view} == {general["id"]}
    assert east_view[0]["customer"]["name"] == "Patient 04"  # who asked, even if they visit another branch
    assert client.get(f"/api/v1/helpdesk/tickets/{t['id']}", headers=east_desk).status_code == 404
    # Assign to a member who answers requests; not to one who cannot.
    agents = client.get("/api/v1/helpdesk/agents", headers=desk).json()
    me = next(a for a in agents if a["name"] == "Front Desk")
    r = client.patch(f"/api/v1/helpdesk/tickets/{t['id']}", json={"assigned_to": me["id"], "priority": "urgent"}, headers=desk)
    assert r.status_code == 200 and r.json()["assigned_to"]["id"] == me["id"] and r.json()["priority"] == "urgent"
    doctor_id = client.get("/api/v1/users/me", headers=doctor).json()["user"]["id"]
    assert client.patch(f"/api/v1/helpdesk/tickets/{t['id']}", json={"assigned_to": doctor_id}, headers=desk).json()["code"] == "invalid_assignee"
    assert client.get("/api/v1/helpdesk/tickets", params={"assigned": "me"}, headers=desk).json()["meta"]["total"] == 1


def test_overdue_auto_resolve_close_and_closed_requests(client, db):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    h, _ = _patient(client, clinic, "9822200005")
    a = _ask(client, clinic, h, subject="First")
    b = _ask(client, clinic, h, subject="Second")
    ta = db.scalar(select(SupportTicket).where(SupportTicket.public_id == a["id"]))
    ta.first_response_due_at = utcnow() - timedelta(hours=1)
    db.commit()
    assert clinic.get("/helpdesk/summary")["overdue"] == 1
    assert clinic.get("/helpdesk/tickets", {"status": "overdue"})["data"][0]["id"] == a["id"]

    client.post(f"/api/v1/helpdesk/tickets/{b['id']}/messages", data={"body": "Can you send the receipt?"}, headers=clinic.h)
    tb = db.scalar(select(SupportTicket).where(SupportTicket.public_id == b["id"]))
    tb.last_activity_at = utcnow() - timedelta(days=8)
    db.commit()
    assert close_stale(db) == 1  # waiting for the patient too long: resolved
    db.refresh(tb)
    assert tb.status == "resolved"
    tb.resolved_at = utcnow() - timedelta(days=8)
    db.commit()
    close_stale(db)
    db.refresh(tb)
    assert tb.status == "closed"
    base = f"/api/v1/customer/organizations/{clinic.org['id']}/requests"
    assert client.post(f"{base}/{b['id']}/messages", data={"body": "One more thing"}, headers=h).json()["code"] == "ticket_closed"

    # Settings are validated; switched off, patients are told to call.
    r = client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/helpdesk", json={"values": {"first_response_hours": 0}}, headers=clinic.h)
    assert r.status_code == 422
    r = client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/helpdesk", json={"values": {"enabled": False}}, headers=clinic.h)
    assert r.status_code == 200
    client.cookies.clear()
    assert _ask(client, clinic, h, expect=403)["code"] == "helpdesk_disabled"


def test_erasing_a_patient_erases_their_requests(client, db):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    h, booking = _patient(client, clinic, "9822200006")
    _ask(client, clinic, h, files={"file": ("x.png", PNG, "image/png")})
    customer_id = clinic.get("/customers", {"search": "Patient 06"})["data"][0]["id"]
    clinic.post(f"/appointments/{booking['id']}/status", {"action": "cancel", "reason": "erase"}, expect=200)
    r = client.post(f"/api/v1/customers/{customer_id}/anonymize", json={"reason": "Patient asked", "confirm": True}, headers=clinic.h)
    assert r.status_code == 200, r.text
    assert db.scalar(select(SupportTicket)) is None and db.scalar(select(SupportMessage)) is None
