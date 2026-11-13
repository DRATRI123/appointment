from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import Appointment, Notification, NotificationLog
from app.notifications import providers as P
from app.notifications.catalog import EVENTS
from app.notifications.providers import DeliveryResult, OutboundMessage
from app.notifications.render import email_html, placeholders, render
from app.services.notification_service import dispatch_due, inr, schedule_reminders, sms_segments
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login
from tests.test_payments import _account, _submit, _verifier


@pytest.fixture(autouse=True)
def _clean_outboxes():
    for ch in ("email", "sms", "whatsapp"):
        P.console_provider(ch).outbox.clear()
        P.console_provider(ch).fail_next.clear()
    yield
    for ch in ("email", "sms", "whatsapp"):
        P.set_provider(ch, None)


def _enable(c: Clinic, **values):
    r = c.client.put("/api/v1/notifications/settings", json={"email_enabled": True, "sms_enabled": True, "whatsapp_enabled": True, **values}, headers=c.h)
    assert r.status_code == 200, r.text
    return r.json()


def _rows(db, **filters):
    stmt = select(Notification)
    for k, v in filters.items():
        stmt = stmt.where(getattr(Notification, k) == v)
    return db.scalars(stmt.order_by(Notification.id)).all()


def _guest_book(c: Clinic, hour=9, mobile="9811100001", email="guest@example.com", whatsapp=True, minute=0):
    hold = c.public_hold(ist(c.monday, hour, minute), session_key=f"n{hour}{minute}")
    return c.public_book(hold["id"], session_key=f"n{hour}{minute}", customer={"full_name": "Asha Patel", "mobile": mobile, "email": email, "whatsapp_opt_in": whatsapp})


# --------------------------------------------------------------- pure functions
def test_catalog_rendering_and_formatting():
    for e in EVENTS.values():
        for ch, t in e.templates.items():
            assert not ((placeholders(t.body) | placeholders(t.subject)) - set(e.variables)), (e.code, ch)
    assert render("Hi {{name}}\n{{missing}}\n\n\n{{ name }}!", {"name": "<b>"}) == "Hi <b>\n\n<b>!"
    html = email_html("Hello <script>\n\nPay at https://x.test/a?b=1&c=2", organization_name="A & B", primary_color="red;}")
    assert "&lt;script&gt;" in html and '<a href="https://x.test/a?b=1&amp;c=2"' in html and "A &amp; B" in html and "red;}" not in html
    assert inr(12345678) == "₹1,23,456.78" and inr(50000) == "₹500.00" and inr(99) == "₹0.99"
    assert sms_segments("a" * 160) == 1 and sms_segments("a" * 161) == 2 and sms_segments("₹" * 71) == 2


# ----------------------------------------------------------- event → outbox
def test_booking_payment_flow_emits_and_dispatches(client, db):
    c = Clinic(client, email="ntf-owner@example.com", name="Notify Clinic")
    _account(c)
    _enable(c)
    appt = _guest_book(c)
    rows = _rows(db, event="appointment.pending_payment")
    assert sorted(r.channel for r in rows) == ["email", "sms", "whatsapp"] and all(r.status == "pending" for r in rows)
    email = next(r for r in rows if r.channel == "email")
    assert "₹500.00" in email.body and f"/o/{c.org['slug']}/appointments/{appt['reference']}?t=" in email.body and email.recipient_address == "guest@example.com"
    assert email.subject.startswith("Complete your payment for Consultation")
    staff = _rows(db, event="staff.new_booking")
    assert [(r.channel, r.status) for r in staff] == [("in_app", "sent"), ("email", "pending")] and staff[1].recipient_address == "ntf-owner@example.com"

    counts = dispatch_due(db, commit=False)
    assert counts["sent"] == 4
    assert P.console_provider("email").outbox[0].html and "Notify Clinic" in P.console_provider("email").outbox[0].html
    sms = P.console_provider("sms").outbox[-1]
    assert "\n" not in sms.body and sms.to == "+919811100001"
    wa = P.console_provider("whatsapp").outbox[-1]
    assert wa.template_params[0] == "Notify Clinic"  # ordered values for provider templates

    _submit(client, c, appt, utr="412300001111")
    ack = _rows(db, event="payment.submitted")
    assert [r.channel for r in ack] == ["email"] and "412300001111" in ack[0].body and "not" not in ack[0].subject.lower()
    assert len(_rows(db, event="staff.payment_to_verify")) == 1

    acc = _verifier(client, c, mobile="9600000031")
    pid = c.get("/payments", {"appointment_id": appt["id"]})["data"][0]["id"]
    client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000}, headers=acc)
    confirmed = _rows(db, event="appointment.confirmed")
    assert sorted(r.channel for r in confirmed) == ["email", "sms", "whatsapp"] and "Paid so far: ₹500.00" in next(r for r in confirmed if r.channel == "email").body

    # Owner's in-app inbox: new booking and the payment to verify; marking read clears the badge.
    inbox = client.get("/api/v1/me/notifications", headers=c.h).json()
    assert inbox["unread"] == 2 and {i["event"] for i in inbox["items"]} == {"staff.new_booking", "staff.payment_to_verify"}
    assert inbox["items"][0]["link"] == "/admin/payments/verification"
    client.post("/api/v1/me/notifications/read", json={"ids": [inbox["items"][0]["id"]]}, headers=c.h)
    assert client.get("/api/v1/me/notifications", headers=c.h).json()["unread"] == 1
    client.post("/api/v1/me/notifications/read", json={}, headers=c.h)
    assert client.get("/api/v1/me/notifications", headers=c.h).json()["unread"] == 0

    # No WhatsApp without opt-in; channels turned off at the organization send nothing.
    _guest_book(c, hour=10, mobile="9811100002", email=None, whatsapp=False)
    latest = _rows(db, event="appointment.pending_payment")[3:]
    assert [r.channel for r in latest] == ["sms"]
    _enable(c, sms_enabled=False, whatsapp_enabled=False)
    _guest_book(c, hour=11, mobile="9811100003", email=None)
    assert len(_rows(db, event="appointment.pending_payment")) == 4

    # Rejection tells the customer why, with a fresh deadline.
    a4 = _guest_book(c, hour=11, minute=30, mobile="9811100004", email="four@example.com")
    _submit(client, c, a4, utr="412300004444")
    p4 = c.get("/payments", {"appointment_id": a4["id"]})["data"][0]["id"]
    client.post(f"/api/v1/admin/payments/{p4}/reject", json={"reason": "No credit found for this UTR"}, headers=acc)
    rej = _rows(db, event="payment.rejected")
    assert len(rej) == 1 and "No credit found for this UTR" in rej[0].body and "412300004444" in rej[0].body


def test_cancellation_reschedule_and_staff_alerts(client, db):
    c = Clinic(client, email="ntf-cancel@example.com", name="Cancel Notify", payment_mode="pay_at_clinic")
    _enable(c, sms_enabled=False, whatsapp_enabled=False)
    user = otp_login(client, "9822200001", "Ravi Kumar")
    client.cookies.clear()
    hold = c.public_hold(ist(c.monday, 9), session_key="cx")
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "cx", "customer": {"full_name": "Ravi Kumar", "email": "ravi@example.com"}}, headers=bearer(user))
    appt = r.json()
    assert appt["status"] == "confirmed"
    # The profile comes from the sign-in (mobile only) and SMS is off, so there was nowhere to send the confirmation.
    assert _rows(db, event="appointment.confirmed") == []
    from app.models import Customer

    row = db.scalar(select(Appointment).where(Appointment.public_id == appt["id"]))
    db.get(Customer, row.customer_id).email = "ravi@example.com"
    db.flush()
    # Staff reschedule → customer told the old and new time.
    c.post(f"/appointments/{appt['id']}/reschedule", {"start_at": ist(c.monday, 11).isoformat(), "reason": "Doctor delayed"}, expect=200)
    resch = _rows(db, event="appointment.rescheduled")
    assert len(resch) == 1 and "9:00 am" in resch[0].body and "11:00 am" in resch[0].body
    # Customer cancels online → customer confirmation plus an in-app alert for staff.
    r = client.post(f"/api/v1/customer/appointments/{appt['id']}/cancel", json={"action": "cancel", "reason": "Travelling"}, headers=bearer(user))
    assert r.status_code == 200, r.text
    assert "Reason: Travelling" in _rows(db, event="appointment.cancelled")[0].body
    alerts = _rows(db, event="staff.appointment_cancelled")
    assert len(alerts) == 1 and alerts[0].channel == "in_app" and "Travelling" in alerts[0].body
    # Customer in-app inbox exists for signed-in customers when in_app is chosen for an event.
    assert client.get("/api/v1/me/notifications", headers=bearer(user)).json()["unread"] == 0


# ------------------------------------------------------------- delivery rules
def test_retry_backoff_permanent_failure_and_admin_actions(client, db):
    c = Clinic(client, email="ntf-retry@example.com", name="Retry Clinic")
    _account(c)
    _enable(c, sms_enabled=False, whatsapp_enabled=False)
    _guest_book(c)
    n = _rows(db, event="appointment.pending_payment")[0]
    P.console_provider("email").fail_next.append(DeliveryResult("console", False, retryable=True, error="HTTP 503"))
    assert dispatch_due(db, commit=False)["retry"] == 1
    db.refresh(n)
    assert n.status == "pending" and n.attempts == 1 and n.scheduled_for > utcnow() and n.last_error == "HTTP 503"
    assert dispatch_due(db, commit=False) == {"sent": 0, "failed": 0, "cancelled": 0, "retry": 0}  # not due yet
    n.scheduled_for = utcnow() - timedelta(seconds=1)
    P.console_provider("email").fail_next.append(DeliveryResult("console", False, retryable=False, error="Mailbox does not exist"))
    assert dispatch_due(db, commit=False)["failed"] == 1
    db.refresh(n)
    assert n.status == "failed" and len(db.scalars(select(NotificationLog).where(NotificationLog.notification_id == n.id)).all()) == 2

    detail = c.get(f"/notifications/{n.public_id}")
    assert detail["status"] == "failed" and [lg["status"] for lg in detail["logs"]] == ["failed", "failed"]
    assert c.get("/notifications", {"status": "failed"})["meta"]["total"] == 1 and c.get("/notifications/stats")["failed"] == 1
    assert client.post(f"/api/v1/notifications/{n.public_id}/retry", headers=c.h).json()["status"] == "pending"
    assert dispatch_due(db, commit=False)["sent"] == 1
    # A broken adapter never stops the worker.
    class Boom:
        name, channel = "boom", "email"
        def configured(self): return True
        def send(self, m): raise RuntimeError("adapter crashed")
    P.set_provider("email", Boom())
    _guest_book(c, hour=10, mobile="9811100009", email="b@example.com")
    assert dispatch_due(db, commit=False)["retry"] == 2  # customer email and the owner's new-booking email
    P.set_provider("email", None)

    # Receptionists cannot see the outbox; other organizations cannot read it.
    rec = _verifier(client, c, role="receptionist", mobile="9600000032")
    assert client.get("/api/v1/notifications", headers=rec).status_code == 403
    other = Clinic(client, email="ntf-other@example.com", name="Other Notify")
    assert client.get(f"/api/v1/notifications/{n.public_id}", headers=other.h).status_code == 404
    assert other.get("/notifications")["meta"]["total"] == 0


def test_reminders_respect_reschedule_cancel_and_preferences(client, db):
    c = Clinic(client, email="ntf-rem@example.com", name="Reminder Clinic", payment_mode="pay_at_clinic")
    _enable(c, sms_enabled=True, whatsapp_enabled=False, reminder_hours=[24, 2])
    appt = c.staff_book(ist(c.monday, 10), customer={"full_name": "Meera Shah", "mobile": "9833300001", "email": "meera@example.com"})
    row = db.scalar(select(Appointment).where(Appointment.public_id == appt["id"]))
    row.created_at = row.confirmed_at = row.start_at - timedelta(days=3)
    db.flush()
    at_24 = row.start_at - timedelta(hours=24)
    assert schedule_reminders(db, now=at_24, commit=False) == 2  # email + sms for the 24 h reminder
    assert schedule_reminders(db, now=at_24, commit=False) == 0  # deduplicated
    rem = _rows(db, event="appointment.reminder")
    assert {r.channel for r in rem} == {"email", "sms"} and "Reminder from Reminder Clinic" in next(r for r in rem if r.channel == "sms").body
    for r in rem:
        r.scheduled_for = utcnow() - timedelta(minutes=1)
    # The appointment moves before the reminder goes out: the stale reminder is cancelled, a new one is created later.
    c.post(f"/appointments/{appt['id']}/reschedule", {"start_at": ist(c.monday, 11).isoformat()}, expect=200)
    assert dispatch_due(db, commit=False)["cancelled"] == 2
    assert all(r.last_error == "appointment was rescheduled" for r in _rows(db, event="appointment.reminder"))
    db.refresh(row)
    assert schedule_reminders(db, now=row.start_at - timedelta(hours=2), commit=False) == 4  # 24 h (late) and 2 h, both channels
    # Cancelled appointments get no reminder.
    for r in _rows(db, event="appointment.reminder", status="scheduled") + _rows(db, event="appointment.reminder", status="pending"):
        r.scheduled_for = utcnow() - timedelta(minutes=1)
    client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert dispatch_due(db, commit=False)["cancelled"] == 4

    # A customer who turned reminders off gets none.
    appt2 = c.staff_book(ist(c.monday, 9), customer={"full_name": "No Reminders", "mobile": "9833300002"})
    row2 = db.scalar(select(Appointment).where(Appointment.public_id == appt2["id"]))
    from app.models import Customer

    cust = db.get(Customer, row2.customer_id)
    cust.communication_preferences = {"reminders": False}
    row2.created_at = row2.confirmed_at = row2.start_at - timedelta(days=3)
    db.flush()
    assert schedule_reminders(db, now=row2.start_at - timedelta(hours=24), commit=False) == 0


# --------------------------------------------------- templates and settings
def test_templates_settings_and_preview(client, db):
    c = Clinic(client, email="ntf-tpl@example.com", name="Template Clinic", payment_mode="pay_at_clinic")
    events = c.get("/notifications/events")
    assert {e["code"] for e in events} == set(EVENTS) and c.get("/notifications/settings")["reminder_hours"] == [24, 2]
    r = client.put("/api/v1/notifications/templates/appointment.confirmed/email", json={"subject": "Hi", "body": "Hello {{patient}}"}, headers=c.h)
    assert r.status_code == 422 and r.json()["code"] == "unknown_variables"
    assert client.put("/api/v1/notifications/templates/appointment.confirmed/email", json={"subject": "", "body": "x"}, headers=c.h).json()["code"] == "subject_required"
    saved = client.put("/api/v1/notifications/templates/appointment.confirmed/email", json={
        "subject": "See you {{appointment_date}}", "body": "Namaste {{customer_name}}, your {{service_name}} is booked.\n\n{{manage_link}}"}, headers=c.h).json()
    assert saved["is_custom"] is True and saved["default_body"].startswith("Hello")
    pv = client.post("/api/v1/notifications/templates/appointment.confirmed/sms/preview", json={"body": "{{organization_name}}: {{service_name}} at {{appointment_time}}"}, headers=c.h).json()
    assert pv["body"] == "Template Clinic: Panchakarma consultation at 10:30 am" and pv["sms_segments"] == 1
    pv = client.post("/api/v1/notifications/templates/appointment.confirmed/email/preview", json={"subject": "S", "body": "Hi {{customer_name}}"}, headers=c.h).json()
    assert "Asha Patel" in pv["html"]

    _enable(c, sms_enabled=False, whatsapp_enabled=False)
    c.staff_book(ist(c.monday, 9), customer={"full_name": "Custom Template", "email": "ct@example.com"})
    n = _rows(db, event="appointment.confirmed")[0]
    assert n.subject.startswith("See you") and n.body.startswith("Namaste Custom Template")
    assert client.delete("/api/v1/notifications/templates/appointment.confirmed/email", headers=c.h).json()["is_custom"] is False

    # Settings are validated; an event can be switched off or routed to other channels.
    assert client.put("/api/v1/notifications/settings", json={"reminder_hours": [500]}, headers=c.h).status_code == 422
    assert client.put("/api/v1/notifications/settings", json={"events": {"nope": {"channels": []}}}, headers=c.h).status_code == 422
    assert client.put("/api/v1/notifications/settings", json={"events": {"staff.new_booking": {"channels": ["sms"]}}}, headers=c.h).status_code == 422
    _enable(c, sms_enabled=False, whatsapp_enabled=False, events={"appointment.confirmed": {"enabled": False, "channels": ["email"]}})
    c.staff_book(ist(c.monday, 10), customer={"full_name": "Silent", "email": "silent@example.com"})
    assert len(_rows(db, event="appointment.confirmed")) == 1

    # Test send goes through the configured provider and is logged.
    t = client.post("/api/v1/notifications/test", json={"channel": "sms", "to": "98111 00099"}, headers=c.h).json()
    assert t["status"] == "sent" and t["logs"][0]["provider"] == "console" and P.console_provider("sms").outbox[-1].to == "+919811100099"
    assert any(p["channel"] == "email" and p["provider"] == "console" for p in c.get("/notifications/providers"))
    rec = _verifier(client, c, role="receptionist", mobile="9600000033")
    assert client.put("/api/v1/notifications/settings", json={}, headers=rec).status_code == 403


# ------------------------------------------------------------- HTTP adapters
def _mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_provider_request_shapes(monkeypatch):
    s = get_settings()
    for k, v in {"twilio_account_sid": "ACtest", "twilio_auth_token": "tok", "twilio_sms_from": "+15550000000", "twilio_whatsapp_from": "whatsapp:+15551111111",
                 "msg91_auth_key": "mkey", "msg91_sender_id": "SUNRSE", "whatsapp_cloud_token": "wtok", "whatsapp_cloud_phone_number_id": "12345"}.items():
        monkeypatch.setattr(s, k, v)
    seen = []

    def twilio(req: httpx.Request):
        seen.append(req)
        return httpx.Response(201, json={"sid": "SM123"})

    r = P.TwilioProvider("sms", _mock(twilio)).send(OutboundMessage(channel="sms", to="+919811100001", body="Hello"))
    form = dict(httpx.QueryParams(seen[-1].content.decode()))
    assert r.ok and r.message_id == "SM123" and seen[-1].url.path.endswith("/Accounts/ACtest/Messages.json") and form == {"To": "+919811100001", "From": "+15550000000", "Body": "Hello"}
    assert seen[-1].headers["authorization"].startswith("Basic ")
    P.TwilioProvider("whatsapp", _mock(twilio)).send(OutboundMessage(channel="whatsapp", to="+919811100001", body="x", provider_template_id="HX1", template_params=["A", "B"]))
    form = dict(httpx.QueryParams(seen[-1].content.decode()))
    assert form["To"] == "whatsapp:+919811100001" and form["ContentSid"] == "HX1" and json.loads(form["ContentVariables"]) == {"1": "A", "2": "B"}
    bad = P.TwilioProvider("sms", _mock(lambda req: httpx.Response(400, json={"message": "invalid To"}))).send(OutboundMessage(channel="sms", to="+91x", body="x"))
    assert not bad.ok and not bad.retryable
    busy = P.TwilioProvider("sms", _mock(lambda req: httpx.Response(429, json={}))).send(OutboundMessage(channel="sms", to="+91x", body="x"))
    assert busy.retryable

    def msg91(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"type": "success", "message": "req-1"})

    m = P.MSG91SMSProvider(_mock(msg91))
    assert not m.send(OutboundMessage(channel="sms", to="+919811100001", body="x")).ok  # needs a DLT flow id
    r = m.send(OutboundMessage(channel="sms", to="+919811100001", body="x", provider_template_id="flow1", template_params=["Asha", "10:30"]))
    body = json.loads(seen[-1].content)
    assert r.ok and r.message_id == "req-1" and seen[-1].headers["authkey"] == "mkey" and body["recipients"] == [{"mobiles": "919811100001", "var1": "Asha", "var2": "10:30"}]

    def meta(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    w = P.MetaWhatsAppProvider(_mock(meta))
    r = w.send(OutboundMessage(channel="whatsapp", to="+919811100001", body="x", provider_template_id="booking_confirmed:en_US", template_params=["Asha", ""]))
    body = json.loads(seen[-1].content)
    assert r.ok and r.message_id == "wamid.1" and seen[-1].url.path == "/v21.0/12345/messages" and seen[-1].headers["authorization"] == "Bearer wtok"
    assert body["template"]["name"] == "booking_confirmed" and body["template"]["language"]["code"] == "en_US"
    assert body["template"]["components"][0]["parameters"] == [{"type": "text", "text": "Asha"}, {"type": "text", "text": "-"}]
    timeout = P.MetaWhatsAppProvider(_mock(lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")))).send(OutboundMessage(channel="whatsapp", to="+91", body="x"))
    assert not timeout.ok and timeout.retryable


def test_smtp_provider(monkeypatch):
    import smtplib

    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.test")
    monkeypatch.setattr(s, "smtp_from", "noreply@clinic.test")
    monkeypatch.setattr(s, "smtp_username", "user")
    monkeypatch.setattr(s, "smtp_password", "pw")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context): sent["tls"] = True
        def login(self, u, p): sent["login"] = u
        def send_message(self, msg):
            sent["msg"] = msg
            return {}

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    r = P.SMTPEmailProvider().send(OutboundMessage(channel="email", to="a@example.com", subject="Hi", body="Text", html="<p>Text</p>", from_name="Sunrise", reply_to="desk@clinic.test"))
    msg = sent["msg"]
    assert r.ok and sent["tls"] and sent["login"] == "user" and msg["From"] == "Sunrise <noreply@clinic.test>" and msg["Reply-To"] == "desk@clinic.test"
    assert msg.get_body(("html",)).get_content().strip() == "<p>Text</p>"

    class Down(FakeSMTP):
        def __init__(self, *a, **k): raise ConnectionRefusedError("refused")

    monkeypatch.setattr(smtplib, "SMTP", Down)
    r = P.SMTPEmailProvider().send(OutboundMessage(channel="email", to="a@example.com", subject="Hi", body="x"))
    assert not r.ok and r.retryable


# --------------------------------------------------------- OTP and preferences
def test_otp_through_notification_providers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_provider", "notifications")
    r = client.post("/api/v1/auth/otp/request", json={"identifier": "9844400001"})
    assert r.status_code == 200 and r.json().get("debug_code") is None  # real delivery never echoes the code
    sms = P.console_provider("sms").outbox[-1]
    code = sms.template_params[0]
    assert sms.to == "+919844400001" and code in sms.body
    assert client.post("/api/v1/auth/otp/verify", json={"identifier": "9844400001", "code": code}).status_code == 200
    client.cookies.clear()
    P.console_provider("email").fail_next.append(DeliveryResult("console", False, error="down"))
    r = client.post("/api/v1/auth/otp/request", json={"identifier": "someone@example.com"})
    assert r.status_code == 503 and r.json()["code"] == "otp_delivery_failed"


def test_customer_preferences(client, db):
    c = Clinic(client, email="ntf-pref@example.com", name="Pref Clinic", payment_mode="pay_at_clinic")
    _enable(c, sms_enabled=True, whatsapp_enabled=True)
    user = otp_login(client, "9855500001", "Kiran Rao")
    client.cookies.clear()
    hold = c.public_hold(ist(c.monday, 9), session_key="pf")
    client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "pf", "customer": {"full_name": "Kiran Rao"}}, headers=bearer(user))
    prefs = client.get("/api/v1/customer/notification-preferences", headers=bearer(user)).json()
    assert prefs == [{"email": True, "sms": True, "whatsapp": False, "reminders": True, "organization_id": c.org["id"], "organization_name": "Pref Clinic", "whatsapp_available": True}]
    assert [n.channel for n in _rows(db, event="appointment.confirmed")] == ["sms"]
    r = client.patch(f"/api/v1/customer/notification-preferences/{c.org['id']}", json={"whatsapp": True, "sms": False}, headers=bearer(user))
    assert r.json()["whatsapp"] is True and r.json()["sms"] is False
    c.post(f"/appointments/{c.get('/appointments')[0]['id']}/reschedule", {"start_at": ist(c.monday, 11).isoformat()}, expect=200)
    assert [n.channel for n in _rows(db, event="appointment.rescheduled")] == ["whatsapp"]
    other = Clinic(client, email="ntf-pref2@example.com", name="Pref Other")
    assert client.patch(f"/api/v1/customer/notification-preferences/{other.org['id']}", json={"sms": False}, headers=bearer(user)).status_code == 404
