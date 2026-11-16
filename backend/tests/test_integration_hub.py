"""Integration Hub: connectors, OAuth, the sync queue, n8n in/out, WhatsApp reports, Tally, API key rotation.

Every provider is simulated with httpx.MockTransport (or a fake client): no real message, contact, invoice or event is
created anywhere.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.connectors.sync import process_due
from app.core.config import get_settings
from app.core.time import utcnow
from app.integrations import http as integration_http
from app.models import Customer, FollowUpTask, Integration, IntegrationSyncItem, Organization, Payment
from app.webhooks.security import sign
from tests.booking_helpers import Clinic, ist


class Fake:
    """Scripted provider: ``routes`` maps "METHOD host/path-prefix" to a response function; every request is kept."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.routes: dict[str, object] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.host}{request.url.path}"
        for prefix, fn in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if key.startswith(prefix):
                return fn(request) if callable(fn) else fn
        return httpx.Response(404, json={"error": f"unexpected {key}"})

    def sent(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if f"{r.method} {r.url.host}{r.url.path}".startswith(prefix)]


@pytest.fixture()
def fake(monkeypatch):
    f = Fake()
    integration_http.set_http_client(httpx.Client(transport=httpx.MockTransport(f)))
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_client_secret", "google-secret")
    yield f
    integration_http.set_http_client(None)


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="hub-owner@example.com", name="Hub Clinic", payment_mode="pay_at_clinic")


def _org(db, c) -> Organization:
    return db.scalar(select(Organization).where(Organization.public_id == c.org["id"]))


def _items(db, provider):
    integ = db.scalar(select(Integration).where(Integration.provider == provider))
    return db.scalars(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id)).all()


def test_overview_lists_every_integration_without_secrets(client, clinic, fake):
    r = clinic.get("/integrations/hub")
    keys = {c["key"] for c in r["cards"]}
    assert {"gmail", "google_contacts", "google_drive", "n8n", "hubspot", "zoho_crm", "zoho_books", "tally", "ga4"} <= keys
    assert {"google_calendar", "google_meet", "zoom", "webhooks", "api_keys", "shopify", "website", "messaging_whatsapp"} <= keys
    assert {c["key"]: c["status"] for c in r["cards"]}["hubspot"] == "not_configured"
    assert {c["key"] for c in r["categories"]} >= {"google", "email", "whatsapp", "sms", "automation", "crm", "accounting", "storage", "analytics", "api", "webhooks"}
    clinic.put("/integrations/hub/hubspot", {"secrets": {"access_token": "pat-na1-very-secret-token-1234"}})
    detail = clinic.get("/integrations/hub/hubspot")
    assert "very-secret" not in json.dumps(detail) and next(f for f in detail["fields"] if f["name"] == "access_token")["hint"] == "…1234"
    assert detail["status"] == "untested"  # Connected only after a real test


def test_hubspot_contacts_sync_without_duplicates_retries_and_erasure(client, db, clinic, fake):
    contacts = {}

    def search(req):
        body = json.loads(req.content)
        value = body["filterGroups"][0]["filters"][0]["value"]
        hit = [cid for cid, props in contacts.items() if value in (props.get("email"), props.get("phone"))]
        return httpx.Response(200, json={"results": [{"id": hit[0]}] if hit else []})

    def create(req):
        cid = str(100 + len(contacts))
        contacts[cid] = json.loads(req.content)["properties"]
        return httpx.Response(201, json={"id": cid})

    fake.routes = {"GET api.hubapi.com/crm/v3/objects/contacts": httpx.Response(200, json={"results": []}),
                   "POST api.hubapi.com/crm/v3/objects/contacts/search": search, "POST api.hubapi.com/crm/v3/objects/contacts": create,
                   "PATCH api.hubapi.com/crm/v3/objects/contacts/": httpx.Response(200, json={}),
                   "DELETE api.hubapi.com/crm/v3/objects/contacts/": httpx.Response(204)}
    clinic.put("/integrations/hub/hubspot", {"secrets": {"access_token": "pat-token-abcdef"}, "values": {"include_city": True}})
    t = clinic.post("/integrations/hub/hubspot/test", {}, expect=200)
    assert t["test"]["ok"] and t["status"] == "connected"
    assert fake.sent("GET api.hubapi.com")[0].headers["authorization"] == "Bearer pat-token-abcdef"

    cust = clinic.post("/customers", {"full_name": "Asha Patel", "mobile": "9811111111", "email": "asha@example.com", "address": {"city": "Pune"}})
    assert [i.status for i in _items(db, "hubspot")] == ["pending"]
    assert process_due(db, commit=False)["synced"] == 1
    assert contacts["100"] == {"firstname": "Asha", "lastname": "Patel", "email": "asha@example.com", "phone": "+919811111111", "city": "Pune"}
    # Nothing changed: nothing is sent again. A change: an update of the same contact, never a second contact.
    clinic.client.patch(f"/api/v1/customers/{cust['id']}", json={"tags": ["vip"]}, headers=clinic.h)
    before = len(fake.requests)
    process_due(db, commit=False)
    assert len(fake.requests) == before  # tags are not sent to HubSpot, so nothing to do
    clinic.client.patch(f"/api/v1/customers/{cust['id']}", json={"full_name": "Asha R Patel"}, headers=clinic.h)
    process_due(db, commit=False)
    assert len(contacts) == 1 and fake.sent("PATCH api.hubapi.com/crm/v3/objects/contacts/100")

    # A temporary failure waits and retries; a revoked token stops and asks to reconnect.
    fake.routes["PATCH api.hubapi.com/crm/v3/objects/contacts/"] = httpx.Response(503, json={"message": "down"})
    clinic.client.patch(f"/api/v1/customers/{cust['id']}", json={"full_name": "Asha Patel"}, headers=clinic.h)
    process_due(db, commit=False)
    item = _items(db, "hubspot")[0]
    assert item.status == "failed" and item.attempts == 1 and item.next_attempt_at > utcnow()
    item.next_attempt_at = utcnow() - timedelta(seconds=1)
    fake.routes["PATCH api.hubapi.com/crm/v3/objects/contacts/"] = httpx.Response(401, json={"message": "expired"})
    process_due(db, commit=False)
    integ = db.scalar(select(Integration).where(Integration.provider == "hubspot"))
    assert integ.status == "error" and clinic.get("/integrations/hub/hubspot")["status"] == "error"

    # Erasure on request removes the CRM contact too.
    fake.routes["PATCH api.hubapi.com/crm/v3/objects/contacts/"] = httpx.Response(200, json={})
    clinic.post("/integrations/hub/hubspot/test", {}, expect=200)
    clinic.post(f"/customers/{cust['id']}/anonymize", {"reason": "Written request", "confirm": True}, expect=200)
    item = _items(db, "hubspot")[0]
    item.next_attempt_at = utcnow()
    process_due(db, commit=False)
    assert fake.sent("DELETE api.hubapi.com/crm/v3/objects/contacts/100") and _items(db, "hubspot")[0].external_id is None


def test_zoho_crm_oauth_connects_once_and_records_the_data_centre(client, db, clinic, fake):
    fake.routes = {"POST accounts.zoho.eu/oauth/v2/token": httpx.Response(200, json={"access_token": "zat", "refresh_token": "zrt", "expires_in": 3600,
                                                                                      "api_domain": "https://www.zohoapis.eu"}),
                   "GET www.zohoapis.eu/crm/v7/users": httpx.Response(200, json={"users": [{"email": "owner@clinic.example"}]})}
    r = client.post("/api/v1/integrations/hub/zoho_crm/connect", json={"return_to": "/admin/integrations/zoho_crm"}, headers=clinic.h)
    assert r.status_code == 422 and r.json()["code"] == "zoho_client_missing"
    clinic.put("/integrations/hub/zoho_crm", {"values": {"client_id": "1000.ABC"}, "secrets": {"client_secret": "zsecret"}})
    url = clinic.post("/integrations/hub/zoho_crm/connect", {"return_to": "/admin/integrations/zoho_crm"}, expect=200)["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.zoho.in/oauth/v2/auth") and q["access_type"] == ["offline"] and "ZohoCRM.modules.contacts.ALL" in q["scope"][0]
    # The account lives in the EU data centre: Zoho says so in accounts-server.
    cb = client.get("/api/v1/integrations/hub/zoho/callback", params={"code": "c1", "state": q["state"][0], "accounts-server": "https://accounts.zoho.eu"},
                    follow_redirects=False)
    assert cb.status_code == 302 and cb.headers["location"].endswith("/admin/integrations/zoho_crm?connected=connected")
    detail = clinic.get("/integrations/hub/zoho_crm")
    assert detail["status"] == "connected" and detail["account"] == "owner@clinic.example"
    assert next(f for f in detail["fields"] if f["name"] == "data_center")["value"] == "eu"
    token_call = fake.sent("POST accounts.zoho.eu/oauth/v2/token")[0]
    assert parse_qs(token_call.content.decode())["client_secret"] == ["zsecret"]
    again = client.get("/api/v1/integrations/hub/zoho/callback", params={"code": "c1", "state": q["state"][0]}, follow_redirects=False)
    assert again.headers["location"].endswith("connected=invalid_state")  # a state works once


def _connect_google(client, clinic, fake, key, scope):
    fake.routes.update({
        "POST oauth2.googleapis.com/token": httpx.Response(200, json={"access_token": "gat", "refresh_token": "grt", "expires_in": 3600, "scope": f"openid email {scope}"}),
        "GET openidconnect.googleapis.com/v1/userinfo": httpx.Response(200, json={"email": "clinic@gmail.example"}),
    })
    url = clinic.post(f"/integrations/hub/{key}/connect", {"return_to": f"/admin/integrations/{key}"}, expect=200)["url"]
    q = parse_qs(urlparse(url).query)
    assert scope in q["scope"][0] and q["access_type"] == ["offline"]
    cb = client.get("/api/v1/integrations/google/callback", params={"code": "g1", "state": q["state"][0]}, follow_redirects=False)
    assert "connected" in cb.headers["location"], cb.headers["location"]
    assert clinic.get(f"/integrations/hub/{key}")["status"] == "connected"


def test_google_contacts_and_drive_use_the_clinics_own_google_account(client, db, clinic, fake, tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.EncryptingStorage(storage_module.LocalStorage(tmp_path))
    try:
        fake.routes = {"GET people.googleapis.com/v1/people:searchContacts": httpx.Response(200, json={"results": []}),
                       "POST people.googleapis.com/v1/people:createContact": httpx.Response(200, json={"resourceName": "people/c42", "etag": "e1"}),
                       "POST www.googleapis.com/drive/v3/files": httpx.Response(200, json={"id": "folder-1"}),
                       "POST www.googleapis.com/upload/drive/v3/files": httpx.Response(200, json={"id": "file-9"})}
        _connect_google(client, clinic, fake, "google_contacts", "https://www.googleapis.com/auth/contacts")
        _connect_google(client, clinic, fake, "google_drive", "https://www.googleapis.com/auth/drive.file")
        cust = clinic.post("/customers", {"full_name": "Ravi Kumar", "mobile": "9822222222"})
        process_due(db, commit=False)
        body = json.loads(fake.sent("POST people.googleapis.com/v1/people:createContact")[0].content)
        assert body == {"names": [{"givenName": "Ravi", "familyName": "Kumar"}], "phoneNumbers": [{"value": "+919822222222", "type": "mobile"}]}

        files = {"file": ("report.pdf", b"%PDF-1.4 lab report", "application/pdf")}
        r = client.post(f"/api/v1/customers/{cust['id']}/documents", files=files, data={"title": "Lab report", "document_type": "report"}, headers=clinic.h)
        assert r.status_code == 201, r.text
        process_due(db, commit=False)
        upload = fake.sent("POST www.googleapis.com/upload/drive/v3/files")[0]
        assert b"%PDF-1.4 lab report" in upload.content and b'"parents": ["folder-1"]' in upload.content
        assert upload.headers["authorization"] == "Bearer gat"
        assert "permissions" not in " ".join(str(r.url) for r in fake.requests)  # nothing is ever shared
    finally:
        storage_module._storage = None


def test_gmail_sends_clinic_emails_and_falls_back_when_it_fails(client, db, clinic, fake):
    from app.notifications.providers import console_provider
    from app.services.connector_service import gmail_sender

    fake.routes["POST gmail.googleapis.com/gmail/v1/users/me/messages/send"] = httpx.Response(200, json={"id": "m-1"})
    _connect_google(client, clinic, fake, "gmail", "https://www.googleapis.com/auth/gmail.send")
    r = clinic.post("/integrations/hub/gmail/test", {"to": "owner@example.com"}, expect=200)
    assert r["test"]["ok"] and "owner@example.com" in r["test"]["message"], r["test"]
    raw = json.loads(fake.sent("POST gmail.googleapis.com")[0].content)["raw"]
    import base64

    assert b"To: owner@example.com" in base64.urlsafe_b64decode(raw + "==")
    provider = gmail_sender(db, _org(db, clinic).id)
    assert provider is not None and provider.name == "gmail"
    fake.routes["POST gmail.googleapis.com/gmail/v1/users/me/messages/send"] = httpx.Response(429, json={"error": {"message": "limit"}})
    from app.notifications.providers import FallbackProvider, OutboundMessage

    before = len(console_provider("email").outbox)
    result = FallbackProvider(provider, console_provider("email")).send(OutboundMessage(channel="email", to="p@example.com", body="Hi", subject="Hi"))
    assert result.ok and result.provider == "console" and len(console_provider("email").outbox) == before + 1


def _verified_payment(db, org, customer_id: int, amount=50000) -> Payment:
    p = Payment(organization_id=org.id, reference=f"PAY-{time.time_ns()}", customer_id=customer_id, method="cash", status="verified",
                amount_paise=amount, verified_amount_paise=amount, verified_at=utcnow())
    db.add(p)
    db.flush()
    return p


def test_zoho_books_sends_verified_payments_once_even_after_a_failure(client, db, clinic, fake):
    from app.webhooks.hooks import on_payment

    calls = {"inv": 0}

    def invoice(req):
        calls["inv"] += 1
        return httpx.Response(201, json={"invoice": {"invoice_id": "INV-1"}})

    fake.routes = {"POST accounts.zoho.in/oauth/v2/token": httpx.Response(200, json={"access_token": "zat", "refresh_token": "zrt", "expires_in": 3600}),
                   "GET www.zohoapis.in/books/v3/organizations": httpx.Response(200, json={"organizations": [{"organization_id": "777", "name": "Hub Books"}]}),
                   "POST www.zohoapis.in/books/v3/contacts": httpx.Response(201, json={"contact": {"contact_id": "C-1"}}),
                   "POST www.zohoapis.in/books/v3/invoices": invoice,
                   "POST www.zohoapis.in/books/v3/customerpayments": httpx.Response(500, json={"message": "busy"})}
    clinic.put("/integrations/hub/zoho_books", {"values": {"client_id": "1000.B"}, "secrets": {"client_secret": "bs"}})
    q = parse_qs(urlparse(clinic.post("/integrations/hub/zoho_books/connect", {}, expect=200)["url"]).query)
    client.get("/api/v1/integrations/hub/zoho/callback", params={"code": "c", "state": q["state"][0]}, follow_redirects=False)
    assert clinic.get("/integrations/hub/zoho_books")["status"] == "connected"
    org = _org(db, clinic)
    cust = db.get(Customer, db.scalar(select(Customer.id).where(Customer.organization_id == org.id).limit(1))) or Customer(organization_id=org.id, full_name="Meera Shah", mobile="+919833333333")
    if cust.id is None:
        db.add(cust)
        db.flush()
    unverified = Payment(organization_id=org.id, reference="PAY-UNVERIFIED", customer_id=cust.id, method="cash", status="submitted", amount_paise=100)
    db.add(unverified)
    db.flush()
    on_payment(db, org, unverified, "payment.submitted")
    assert not _items(db, "zoho_books")  # never sent before verification
    p = _verified_payment(db, org, cust.id)
    on_payment(db, org, p, "payment.verified")
    process_due(db, commit=False)
    item = next(i for i in _items(db, "zoho_books") if i.entity_type == "payment")
    assert item.status == "failed" and item.external_id == "inv:INV-1"  # the invoice id is kept
    fake.routes["POST www.zohoapis.in/books/v3/customerpayments"] = httpx.Response(201, json={"payment": {"payment_id": "P-1"}})
    item.next_attempt_at = utcnow()
    process_due(db, commit=False)
    assert item.status == "synced" and item.external_id == "inv:INV-1|pay:P-1" and calls["inv"] == 1
    pay = json.loads(fake.sent("POST www.zohoapis.in/books/v3/customerpayments")[-1].content)
    assert pay["amount"] == 500.0 and pay["invoices"] == [{"invoice_id": "INV-1", "amount_applied": 500.0}]
    assert fake.sent("POST www.zohoapis.in/books/v3/invoices")[0].url.params["organization_id"] == "777"


def test_tally_export_has_vouchers_once_and_needs_payment_permission(client, db, clinic):
    org = _org(db, clinic)
    cust = Customer(organization_id=org.id, full_name="Kiran & Co <test>", mobile="+919844444444")
    db.add(cust)
    db.flush()
    p = _verified_payment(db, org, cust.id, 75000)
    clinic.put("/integrations/hub/tally", {"values": {"company_name": "Hub Clinic"}})
    today = date.today().isoformat()
    r = client.get("/api/v1/integrations/hub/tally/export", params={"from": today, "to": today}, headers=clinic.h)
    assert r.status_code == 200 and r.headers["x-voucher-count"] == "1"
    xml = r.text
    assert f'REMOTEID="{p.public_id}"' in xml and "<AMOUNT>-750.00</AMOUNT>" in xml and "Kiran &amp; Co &lt;test&gt;" in xml
    assert "<LEDGERNAME>Cash</LEDGERNAME>" in xml and "<SVCURRENTCOMPANY>Hub Clinic</SVCURRENTCOMPANY>" in xml
    again = client.get("/api/v1/integrations/hub/tally/export", params={"from": today, "to": today}, headers=clinic.h)
    assert again.headers["x-voucher-count"] == "0"  # already exported
    assert client.get("/api/v1/integrations/hub/tally/export", params={"from": today, "to": today, "include_exported": "true"},
                      headers=clinic.h).headers["x-voucher-count"] == "1"


def _signed(secret: str, body: dict, request_id: str, ts: int | None = None):
    raw = json.dumps(body).encode()
    ts = ts or int(time.time())
    return raw, {"X-Webhook-Signature": sign(secret, ts, raw), "X-Request-Id": request_id, "Content-Type": "application/json"}


def test_n8n_events_out_and_signed_actions_in(client, db, clinic, fake):
    fake.routes["POST n8n.example.com/webhook/clinic"] = httpx.Response(200, json={"ok": True})
    saved = clinic.put("/integrations/hub/n8n", {"values": {"url": "https://n8n.example.com/webhook/clinic", "events": "appointment.created, customer.created",
                                                            "allowed_actions": "get_appointment, create_follow_up, update_customer"}})
    secrets = saved["shown_once"]
    assert secrets["outgoing_secret"].startswith("whsec_") and secrets["incoming_secret"].startswith("whsec_")
    assert "incoming_secret" not in json.dumps(clinic.get("/integrations/hub/n8n"))  # never shown again
    t = clinic.post("/integrations/hub/n8n/test", {}, expect=200)
    assert t["status"] == "connected"
    ping = fake.sent("POST n8n.example.com")[-1]
    from app.webhooks.security import verify

    assert verify(secrets["outgoing_secret"], ping.headers["x-webhook-signature"], ping.content, now=int(time.time()))

    appt = clinic.staff_book(ist(clinic.monday, 9), customer={"full_name": "Auto Guest", "mobile": "9855555555"})
    url = f"/api/v1/automation/n8n/{saved['id'] if 'id' in saved else db.scalar(select(Integration.public_id).where(Integration.provider == 'n8n'))}"
    secret = secrets["incoming_secret"]
    raw, h = _signed(secret, {"action": "get_appointment", "data": {"reference": appt["reference"]}}, "req-00000001")
    r = client.post(url, content=raw, headers=h)
    assert r.status_code == 200 and r.json()["appointment"]["reference"] == appt["reference"]
    assert client.post(url, content=raw, headers=h).status_code == 409  # replay refused
    raw2, h2 = _signed(secret, {"action": "get_appointment", "data": {"reference": appt["reference"]}}, "req-00000002", ts=int(time.time()) - 900)
    assert client.post(url, content=raw2, headers=h2).status_code == 401  # too old
    raw3, h3 = _signed("whsec_wrong", {"action": "get_appointment", "data": {}}, "req-00000003")
    assert client.post(url, content=raw3, headers=h3).status_code == 401
    raw4, h4 = _signed(secret, {"action": "send_notification", "data": {"reference": appt["reference"], "event": "appointment.reminder"}}, "req-00000004")
    assert client.post(url, content=raw4, headers=h4).json()["code"] == "action_not_allowed"
    raw5, h5 = _signed(secret, {"action": "create_follow_up", "data": {"reference": appt["reference"], "title": "Call about report", "due_at": "2026-12-01T10:00:00+05:30"}}, "req-00000005")
    task = client.post(url, content=raw5, headers=h5).json()["task"]
    assert task["title"] == "Call about report" and db.scalar(select(FollowUpTask).where(FollowUpTask.public_id == task["id"])).source == "n8n"
    assert [t["title"] for t in clinic.get("/integrations/hub/tasks")] == ["Call about report"]
    cust_id = appt["customer"]["id"] if isinstance(appt.get("customer"), dict) else db.scalar(select(Customer.public_id).where(Customer.full_name == "Auto Guest"))
    raw6, h6 = _signed(secret, {"action": "update_customer", "data": {"customer_id": cust_id, "full_name": "Hacked", "tags": ["follow-up"]}}, "req-00000006")
    assert client.post(url, content=raw6, headers=h6).status_code == 200
    c = db.scalar(select(Customer).where(Customer.public_id == cust_id))
    assert c.tags == ["follow-up"] and c.full_name == "Auto Guest"  # only tags and preferences can change
    # Rotation: old incoming secret stops working.
    new = clinic.post("/integrations/hub/n8n/rotate", {}, expect=200)["shown_once"]["incoming_secret"]
    raw7, h7 = _signed(secret, {"action": "get_appointment", "data": {"reference": appt["reference"]}}, "req-00000007")
    assert client.post(url, content=raw7, headers=h7).status_code == 401
    raw8, h8 = _signed(new, {"action": "get_appointment", "data": {"reference": appt["reference"]}}, "req-00000008")
    assert client.post(url, content=raw8, headers=h8).status_code == 200


def test_whatsapp_delivery_reports_and_stop_replies(client, db, clinic, monkeypatch):
    from app.models import Notification, NotificationLog

    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_app_secret", "meta-app-secret")
    monkeypatch.setattr(s, "whatsapp_webhook_verify_token", "verify-me-123")
    ok = client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me-123", "hub.challenge": "4242"})
    assert ok.status_code == 200 and ok.text == "4242"
    assert client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403
    org = _org(db, clinic)
    cust = Customer(organization_id=org.id, full_name="Opt Out", mobile="+919866666666", communication_preferences={"whatsapp": True})
    db.add(cust)
    db.flush()
    n = Notification(organization_id=org.id, event="appointment.reminder", channel="whatsapp", body="Reminder", status="sent")
    db.add(n)
    db.flush()
    db.add(NotificationLog(notification_id=n.id, provider="meta", provider_message_id="wamid.ABC", status="sent", created_at=utcnow()))
    db.flush()
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.ABC", "status": "read", "timestamp": str(int(time.time()))}],
                                                 "messages": [{"from": "919866666666", "type": "text", "text": {"body": "stop"}}]}}]}]}
    raw = json.dumps(payload).encode()
    assert client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    sig = "sha256=" + hmac.new(b"meta-app-secret", raw, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert r.status_code == 200 and r.json() == {"ok": True, "statuses": 1, "opt_changes": 1}
    db.refresh(n)
    db.refresh(cust)
    assert n.read_at is not None and cust.communication_preferences["whatsapp"] is False


def test_ga4_ids_are_checked_and_only_public_when_switched_on(client, clinic):
    bad = client.put("/api/v1/integrations/hub/ga4", json={"values": {"measurement_id": "UA-12345"}}, headers=clinic.h)
    assert bad.status_code == 422
    clinic.put("/integrations/hub/ga4", {"values": {"measurement_id": "G-ABC123XYZ"}})
    assert clinic.post("/integrations/hub/ga4/test", {}, expect=200)["status"] == "active"
    pub = client.get(f"/api/v1/public/organizations/{clinic.org['slug']}").json()
    assert pub["settings"]["analytics"] == {"ga4_measurement_id": "G-ABC123XYZ", "gtm_container_id": None}
    clinic.post("/integrations/hub/ga4/enabled", {"enabled": False}, expect=200)
    assert client.get(f"/api/v1/public/organizations/{clinic.org['slug']}").json()["settings"]["analytics"] is None


def test_staff_without_integration_rights_cannot_change_or_read_the_hub(client, db, clinic):
    from tests.helpers import otp_login

    clinic.post(f"/organizations/{clinic.org['id']}/members", {"identifier": "9877777777", "full_name": "Desk", "role_code": "receptionist"})
    desk = {"Authorization": f"Bearer {otp_login(client, '9877777777')['access_token']}", "X-Organization-Id": clinic.org["id"]}
    assert client.get("/api/v1/integrations/hub", headers=desk).status_code == 403
    assert client.put("/api/v1/integrations/hub/hubspot", json={"secrets": {"access_token": "x"}}, headers=desk).status_code == 403


def test_api_key_rotation_keeps_the_old_key_for_the_overlap_and_logs_access(client, db, clinic):
    created = clinic.post("/developers/api-keys", {"name": "Website", "scopes": ["appointments:read"]})
    old = created["key"]
    assert client.get("/api/v1/appointments", headers={"X-API-Key": old}).status_code == 200
    new = clinic.post(f"/developers/api-keys/{created['id']}/rotate", {}, expect=200)
    assert new["key"] != old and new["scopes"] == ["appointments:read"]
    assert client.get("/api/v1/appointments", headers={"X-API-Key": old}).status_code == 200  # 24 hours overlap
    assert client.get("/api/v1/appointments", headers={"X-API-Key": new["key"]}).status_code == 200
    logs = clinic.get(f"/developers/api-keys/{created['id']}/access-logs")
    assert logs and logs[0]["path"] == "/api/v1/appointments" and logs[0]["status"] == 200 and "?" not in logs[0]["path"]


def test_google_sign_in_never_relinks_an_account_to_another_google_identity(client, db):
    from app.models import User
    from app.security.google import GoogleIdentity, set_google_verifier
    from tests.helpers import register

    register(client, "linked@example.com", "Linked Person")
    user = db.scalar(select(User).where(User.email == "linked@example.com"))
    user.google_sub = "google-original"
    db.flush()

    class Verifier:
        def __init__(self, sub):
            self.sub = sub

        def verify(self, token):
            return GoogleIdentity(sub=self.sub, email="linked@example.com", email_verified=True, name="X", picture=None)

    set_google_verifier(Verifier("google-attacker"))
    try:
        r = client.post("/api/v1/auth/google", json={"id_token": "t" * 30})
        assert r.status_code == 401 and r.json()["code"] == "google_account_conflict"
        set_google_verifier(Verifier("google-original"))
        assert client.post("/api/v1/auth/google", json={"id_token": "t" * 30}).status_code == 200
    finally:
        set_google_verifier(None)
    assert client.get("/api/v1/auth/google/config").json() == {"client_id": get_settings().google_client_id or None}
