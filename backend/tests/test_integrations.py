from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.integrations import http as integration_http
from app.integrations.ics import IcsEvent, calendar
from app.models import Appointment, AppointmentExternalEvent, Integration, IntegrationLog, Notification
from app.services.integration_service import pull_all_busy, sync_external
from tests.booking_helpers import Clinic, iso, ist, utc
from tests.helpers import otp_login
from tests.test_payments import _verifier


class FakeProviders:
    """Just enough of Google OAuth/Calendar and Zoom to exercise the real client code."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.external_busy: list[dict] = []
        self.meetings: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail: dict[str, httpx.Response] = {}
        self.refresh_count = 0
        self.last_patch: dict = {}
        self.n = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        key = f"{req.method} {req.url.host}{req.url.path}"
        self.calls.append((req.method, str(req.url)))
        for prefix, resp in list(self.fail.items()):
            if key.startswith(prefix):
                return resp
        host, path = req.url.host, req.url.path
        if host == "oauth2.googleapis.com" and path == "/token":
            form = dict(parse_qs(req.content.decode()))
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-secret", "expires_in": 3600,
                                                 "scope": "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.events"})
            self.refresh_count += 1
            return httpx.Response(200, json={"access_token": f"at-r{self.refresh_count}", "expires_in": 3600})
        if host == "oauth2.googleapis.com" and path == "/revoke":
            return httpx.Response(200)
        if host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "dr.slot@gmail.com"})
        if host == "www.googleapis.com" and "/events" in path:
            parts = path.split("/events")
            event_id = parts[1].strip("/") if len(parts) > 1 else ""
            if req.method == "POST":
                self.n += 1
                body = json.loads(req.content)
                ev = {**body, "id": f"ev{self.n}", "htmlLink": f"https://calendar.google.com/event?eid=ev{self.n}"}
                if "conferenceData" in body and req.url.params.get("conferenceDataVersion") == "1":
                    ev["hangoutLink"] = f"https://meet.google.com/abc-defg-{self.n:03d}"
                self.events[ev["id"]] = ev
                return httpx.Response(200, json=ev)
            if req.method == "PATCH":
                self.last_patch = {"body": json.loads(req.content), "params": dict(req.url.params)}
                self.events[event_id].update(self.last_patch["body"])
                return httpx.Response(200, json=self.events[event_id])
            if req.method == "DELETE":
                return httpx.Response(204) if self.events.pop(event_id, None) else httpx.Response(410, json={"error": {"message": "gone"}})
            items = list(self.external_busy) + [{"start": e["start"], "end": e["end"], "extendedProperties": e["extendedProperties"]} for e in self.events.values()]
            return httpx.Response(200, json={"items": items})
        if host == "zoom.us" and path == "/oauth/token":
            if req.url.params.get("account_id") == "bad-account":
                return httpx.Response(400, json={"reason": "Invalid client_id or client_secret", "error": "invalid_client"})
            return httpx.Response(200, json={"access_token": "zoom-at", "expires_in": 3600})
        if host == "api.zoom.us":
            if req.method == "GET" and path.startswith("/v2/users/"):
                return httpx.Response(200, json={"email": "clinic@zoom.test"})
            if req.method == "POST" and path.endswith("/meetings"):
                self.n += 1
                mid = str(900000 + self.n)
                self.meetings[mid] = json.loads(req.content)
                return httpx.Response(201, json={"id": int(mid), "join_url": f"https://zoom.us/j/{mid}?pwd=x"})
            mid = path.rsplit("/", 1)[-1]
            if req.method == "PATCH":
                self.meetings[mid].update(json.loads(req.content))
                return httpx.Response(204)
            if req.method == "DELETE":
                self.meetings.pop(mid, None)
                return httpx.Response(204)
        return httpx.Response(404, json={"error": f"unexpected {key}"})


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProviders()
    integration_http.set_http_client(httpx.Client(transport=httpx.MockTransport(f)))
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_client_secret", "google-secret")
    yield f
    integration_http.set_http_client(None)


def _online(c: Clinic):
    c.client.patch(f"/api/v1/services/{c.service['id']}", json={"consultation_mode": "online", "payment_mode": "pay_at_clinic"}, headers=c.h)


def _connect_google(client, c: Clinic, fake: FakeProviders, db):
    from tests.helpers import clinic_google_app

    clinic_google_app(db, c.org["id"], client_id="client-123.apps.googleusercontent.com")
    r = client.post("/api/v1/integrations/google/connect", json={"professional_id": c.pro["id"]}, headers=c.h)
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["authorization_url"])
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com" and q["client_id"] == ["client-123.apps.googleusercontent.com"] and q["access_type"] == ["offline"]
    assert "https://www.googleapis.com/auth/calendar.events" in q["scope"][0] and q["redirect_uri"][0].endswith("/api/v1/integrations/google/callback")
    state = q["state"][0]
    cb = client.get("/api/v1/integrations/google/callback", params={"state": state, "code": "auth-code"}, follow_redirects=False)
    assert cb.status_code == 303 and cb.headers["location"].endswith("/admin/integrations?google=connected")
    return state


# ---------------------------------------------------------------- iCalendar
def test_ics_output_and_downloads(client, db):
    text = calendar([IcsEvent("x@y", datetime(2026, 11, 16, 4, tzinfo=UTC), datetime(2026, 11, 16, 4, 30, tzinfo=UTC), "Consult; Dr, A", description="a\nb " + "é" * 60)], name="T")
    bs = chr(92)
    assert f"SUMMARY:Consult{bs}; Dr{bs}, A" in text and "DTSTART:20261116T040000Z" in text and "\r\n " in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    c = Clinic(client, email="ics-owner@example.com", name="ICS Clinic", payment_mode="pay_at_clinic")
    hold = c.public_hold(ist(c.monday, 9), session_key="ics")
    appt = c.public_book(hold["id"], session_key="ics", customer={"full_name": "Ics Guest", "mobile": "9811188001"})
    r = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/calendar.ics", params={"access_token": appt["access_token"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar") and "SUMMARY:Consultation with Dr. Slot" in r.text and "STATUS:CONFIRMED" in r.text
    assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/calendar.ics").status_code == 403
    staff = client.get(f"/api/v1/appointments/{appt['id']}/calendar.ics", headers=c.h)
    assert staff.status_code == 200 and "Ics Guest" in staff.text


# ------------------------------------------------------------ Google Calendar
def test_google_calendar_connect_events_meet_busy_and_sync(client, db, fake):
    c = Clinic(client, email="gcal-owner@example.com", name="GCal Clinic")
    _online(c)
    state = _connect_google(client, c, fake, db)
    integ = db.scalar(select(Integration).where(Integration.provider == "google_calendar"))
    assert integ.status == "connected" and integ.external_account_id == "dr.slot@gmail.com"
    assert "rt-secret" not in (integ.credentials_encrypted or "") and integ.credentials_encrypted.startswith("enc:")
    # The state is single use.
    again = client.get("/api/v1/integrations/google/callback", params={"state": state, "code": "x"}, follow_redirects=False)
    assert again.headers["location"].endswith("google=invalid_state")
    assert client.get("/api/v1/integrations/google/callback", params={"state": "forged", "code": "x"}, follow_redirects=False).headers["location"].endswith("google=invalid_state")

    # Busy time from the doctor's own calendar blocks slots; our own events never do.
    fake.external_busy.append({"start": {"dateTime": iso(ist(c.monday, 10))}, "end": {"dateTime": iso(ist(c.monday, 10, 30))}})
    integ.config = {**integ.config, "busy_pulled_at": ""}
    db.flush()
    assert pull_all_busy(db, commit=False) == 1
    assert iso(utc(ist(c.monday, 10))) not in c.slot_starts(c.monday) and iso(utc(ist(c.monday, 9))) in c.slot_starts(c.monday)

    # Confirmed online appointment → calendar event with a Meet link; the customer is told the link.
    appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Online Guest", "mobile": "9811188002", "email": "og@example.com"}, consultation_mode="online")
    assert appt["status"] == "confirmed"
    assert sync_external(db, commit=False)["synced"] == 1
    row = db.scalar(select(AppointmentExternalEvent))
    ev = fake.events[row.external_id]
    assert ev["summary"] == "Consultation · Online Guest" and ev["extendedProperties"]["private"]["appointment_platform_id"] == appt["id"]
    assert ev["start"]["timeZone"] == "Asia/Kolkata" and ev["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    detail = c.get(f"/appointments/{appt['id']}")
    assert detail["meeting_link"] == "https://meet.google.com/abc-defg-001"
    link_msgs = db.scalars(select(Notification).where(Notification.event == "appointment.meeting_link")).all()
    assert link_msgs and "https://meet.google.com/abc-defg-001" in link_msgs[0].body
    # Our event is not imported as busy time.
    integ.config = {**integ.config, "busy_pulled_at": ""}
    db.flush()
    assert pull_all_busy(db, commit=False) == 1

    # Reschedule → patched (no second Meet); cancel → deleted.
    c.post(f"/appointments/{appt['id']}/reschedule", {"start_at": iso(ist(c.monday, 11))}, expect=200)
    assert sync_external(db, commit=False)["synced"] == 1
    assert fake.events[row.external_id]["start"]["dateTime"].startswith(ist(c.monday, 11).astimezone(UTC).isoformat()[:16])
    assert "conferenceData" not in fake.last_patch["body"] and "conferenceDataVersion" not in fake.last_patch["params"] and len(fake.events) == 1
    assert c.get(f"/appointments/{appt['id']}")["meeting_link"] == "https://meet.google.com/abc-defg-001"  # same link after the move
    client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert sync_external(db, commit=False)["deleted"] == 1
    assert fake.events == {} and db.get(AppointmentExternalEvent, row.id).status == "deleted"

    # Expired access token is refreshed transparently.
    from app.services.integration_service import _creds, _save_creds

    creds = _creds(integ)
    creds["expires_at"] = (utcnow() - timedelta(minutes=1)).isoformat()
    _save_creds(integ, creds)
    appt2 = c.staff_book(ist(c.monday, 9, 30), customer={"full_name": "Second", "mobile": "9811188003"})
    sync_external(db, commit=False)
    assert fake.refresh_count == 1 and len(fake.events) == 1

    # Google outage → retried with backoff; revoked access → integration needs reconnecting.
    fake.fail["POST www.googleapis.com"] = httpx.Response(503, json={"error": {"message": "backend error"}})
    c.staff_book(ist(c.monday, 10, 30), customer={"full_name": "Third", "mobile": "9811188004"})
    assert sync_external(db, commit=False)["retry"] == 1
    pending = db.scalar(select(AppointmentExternalEvent).where(AppointmentExternalEvent.status == "pending"))
    assert pending.next_attempt_at > utcnow() and "503" in pending.last_error
    fake.fail.clear()
    fake.fail["POST oauth2.googleapis.com/token"] = httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    creds = _creds(integ)
    creds["expires_at"] = (utcnow() - timedelta(minutes=1)).isoformat()
    _save_creds(integ, creds)
    pending.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert sync_external(db, commit=False)["failed"] == 1
    db.refresh(integ)
    assert integ.status == "error" and "Reconnect" in integ.last_error
    issues = c.get("/integrations/sync-issues")
    assert any(i["status"] == "failed" for i in issues)
    assert db.scalars(select(IntegrationLog).where(IntegrationLog.integration_id == integ.id, IntegrationLog.status == "failed")).first() is not None
    overview = c.get("/integrations")
    assert overview["google_configured"] is True and overview["professionals"][0]["google"]["status"] == "error"

    # Disconnect revokes, drops busy blocks and stops syncing.
    fake.fail.clear()
    assert client.delete(f"/api/v1/integrations/{integ.public_id}", headers=c.h).status_code == 200
    assert any(u.endswith("/revoke") for _, u in fake.calls)
    db.refresh(integ)
    assert integ.status == "disconnected" and integ.credentials_encrypted is None
    assert iso(utc(ist(c.monday, 10))) in c.slot_starts(c.monday)
    _ = appt2


# ---------------------------------------------------------------------- Zoom
def test_zoom_meetings(client, db, fake):
    c = Clinic(client, email="zoom-owner@example.com", name="Zoom Clinic")
    _online(c)
    r = client.post("/api/v1/integrations/zoom", json={"account_id": "bad-account", "client_id": "cid1", "client_secret": "sec1"}, headers=c.h)
    assert r.status_code == 422 and r.json()["code"] == "zoom_rejected"
    z = client.post("/api/v1/integrations/zoom", json={"account_id": "acct-1", "client_id": "cid1", "client_secret": "sec1"}, headers=c.h).json()
    assert z["status"] == "connected" and z["account"] == "clinic@zoom.test" and "sec1" not in json.dumps(z)
    pref = c.get(f"/integrations/professionals/{c.pro['id']}/meeting")
    assert pref["provider"] == "auto" and c.get("/integrations")["professionals"][0]["effective_meeting_provider"] == "zoom"
    client.put(f"/api/v1/integrations/professionals/{c.pro['id']}/meeting", json={"provider": "zoom", "zoom_user": "dr@clinic.test"}, headers=c.h)
    appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Zoom Guest", "mobile": "9811188101"}, consultation_mode="online")
    assert sync_external(db, commit=False)["synced"] == 1
    mid, meeting = next(iter(fake.meetings.items()))
    assert meeting["topic"] == "Zoom Clinic: Consultation" and meeting["settings"]["waiting_room"] is True and meeting["start_time"].endswith("Z")
    assert any("/users/dr@clinic.test/meetings" in u or "/users/dr%40clinic.test/meetings" in u for _, u in fake.calls)
    assert c.get(f"/appointments/{appt['id']}")["meeting_link"] == f"https://zoom.us/j/{mid}?pwd=x"
    # Every online appointment gets its own meeting; in-person ones get none.
    c.staff_book(ist(c.monday, 10), customer={"full_name": "Second Online", "mobile": "9811188102"}, consultation_mode="online")
    client.patch(f"/api/v1/services/{c.service['id']}", json={"consultation_mode": "both"}, headers=c.h)
    c.staff_book(ist(c.monday, 11), customer={"full_name": "Visit", "mobile": "9811188103"}, consultation_mode="in_person")
    sync_external(db, commit=False)
    assert len(fake.meetings) == 2
    client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert sync_external(db, commit=False)["deleted"] == 1 and mid not in fake.meetings


# --------------------------------------------------- manual links + access
def test_manual_links_feeds_and_permissions(client, db, fake):
    c = Clinic(client, email="manual-owner@example.com", name="Manual Clinic")
    from tests.helpers import clinic_google_app

    clinic_google_app(db, c.org["id"])
    _online(c)
    client.put("/api/v1/notifications/settings", json={"email_enabled": True}, headers=c.h)
    bad = client.put(f"/api/v1/integrations/professionals/{c.pro['id']}/meeting", json={"provider": "manual", "manual_url": "http://insecure.test/room"}, headers=c.h)
    assert bad.status_code == 422
    client.put(f"/api/v1/integrations/professionals/{c.pro['id']}/meeting", json={"provider": "manual", "manual_url": "https://meet.example.com/dr-slot"}, headers=c.h)
    appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Manual Guest", "email": "mg@example.com"}, consultation_mode="online")
    assert c.get(f"/appointments/{appt['id']}")["meeting_link"] == "https://meet.example.com/dr-slot"
    confirmation = db.scalar(select(Notification).where(Notification.event == "appointment.confirmed", Notification.channel == "email"))
    assert "Join online: https://meet.example.com/dr-slot" in confirmation.body
    # A link set on one appointment overrides and tells the customer.
    r = client.put(f"/api/v1/appointments/{appt['id']}/meeting", json={"meeting_link": "https://zoom.us/j/555"}, headers=c.h)
    assert r.status_code == 200 and c.get(f"/appointments/{appt['id']}")["meeting_link"] == "https://zoom.us/j/555"
    assert db.scalar(select(Notification).where(Notification.event == "appointment.meeting_link", Notification.channel == "email")) is not None
    assert client.put(f"/api/v1/appointments/{appt['id']}/meeting", json={"meeting_link": "javascript:alert(1)"}, headers=c.h).status_code == 422

    # Private calendar feed: rotate gives a new secret URL; the old one stops working.
    url = client.post(f"/api/v1/integrations/professionals/{c.pro['id']}/feed", headers=c.h).json()["detail"]
    path = "/api/v1/" + url.split("/api/v1/", 1)[1]
    feed = client.get(path)
    assert feed.status_code == 200 and "Manual Guest" in feed.text and "BEGIN:VCALENDAR" in feed.text
    new_url = client.post(f"/api/v1/integrations/professionals/{c.pro['id']}/feed", headers=c.h).json()["detail"]
    assert client.get(path).status_code == 404 and new_url != url
    assert client.get("/api/v1/calendar-feeds/nope.ics").status_code == 404

    # Permissions: receptionists cannot connect Zoom; a doctor manages only their own professional; other orgs see nothing.
    rec = _verifier(client, c, role="receptionist", mobile="9600000041")
    assert client.post("/api/v1/integrations/zoom", json={"account_id": "acct-1", "client_id": "cid1", "client_secret": "sec1"}, headers=rec).status_code == 403
    assert client.get("/api/v1/integrations", headers=rec).status_code == 403
    doc_h = _verifier(client, c, role="doctor", mobile="9600000042")
    me = otp_login(client, "9600000042")
    client.cookies.clear()
    from app.models import Professional, User

    pro = db.scalar(select(Professional).where(Professional.public_id == c.pro["id"]))
    pro.user_id = db.scalar(select(User.id).where(User.public_id == me["user"]["id"]))
    other_pro = c.post("/professionals", {"display_name": "Dr. Other", "branches": [{"branch_id": c.branch["id"]}], "services": [{"service_id": c.service["id"]}]})
    db.flush()
    ov = client.get("/api/v1/integrations", headers=doc_h).json()
    assert [p["professional_name"] for p in ov["professionals"]] == ["Dr. Slot"] and ov["professionals"][0]["is_me"] is True and ov["can_manage_all"] is False
    assert client.put(f"/api/v1/integrations/professionals/{c.pro['id']}/meeting", json={"provider": "none"}, headers=doc_h).status_code == 200
    assert client.put(f"/api/v1/integrations/professionals/{other_pro['id']}/meeting", json={"provider": "none"}, headers=doc_h).status_code == 403
    assert client.post("/api/v1/integrations/google/connect", json={"professional_id": other_pro["id"]}, headers=doc_h).status_code == 403
    assert client.post("/api/v1/integrations/google/connect", json={"professional_id": c.pro["id"]}, headers=doc_h).status_code == 200
    other = Clinic(client, email="manual-other@example.com", name="Other Manual")
    assert client.put(f"/api/v1/appointments/{appt['id']}/meeting", json={"meeting_link": None}, headers=other.h).status_code == 404
    assert client.post("/api/v1/integrations/google/connect", json={"professional_id": c.pro["id"]}, headers=other.h).status_code == 404


def test_google_not_configured(client, monkeypatch):
    # The platform's Google key is only for Sign in with Google: without the clinic's own Google app, no connection.
    monkeypatch.setattr(get_settings(), "google_client_id", "platform-signin.apps.googleusercontent.com")
    monkeypatch.setattr(get_settings(), "google_client_secret", "platform-secret")
    c = Clinic(client, email="nogoogle@example.com", name="No Google")
    r = client.post("/api/v1/integrations/google/connect", json={"professional_id": c.pro["id"]}, headers=c.h)
    assert r.status_code == 422 and r.json()["code"] == "google_not_configured"
    assert c.get("/integrations")["google_configured"] is False
    _ = Appointment
