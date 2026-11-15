"""Multi-channel one-time codes for public bookings: SMS, WhatsApp and email.

Covers the booking flow end to end, every security rule (hashing, expiry, single use, attempts, resend cool-down and
cap, superseded codes, per destination / IP / session limits, session ownership, token binding to the contact being
booked), the admin policy and the clinic's own delivery accounts (encrypted secrets, exact provider requests).
"""
from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.time import utcnow
from app.models.verification import MessagingProviderConfig, OtpChallenge
from app.notifications import providers as P
from app.notifications.providers import DeliveryResult, console_provider
from app.security.rate_limit import limiter
from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, otp_login

MOBILE = "9812300001"
E164 = "+919812300001"
EMAIL = "asha.patel@example.com"


@pytest.fixture(autouse=True)
def _clean_outboxes():
    for ch in ("sms", "whatsapp", "email"):
        console_provider(ch).outbox.clear()
        console_provider(ch).fail_next.clear()
    yield


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="otp-owner@example.com", name="Akshar Clinic", payment_mode="pay_at_clinic", verify_mobile=True)


def pub(c: Clinic) -> str:
    return f"/api/v1/public/organizations/{c.org['slug']}"


def hold(client, c: Clinic, hour: int = 9, key: str = "otp-session-1") -> dict:
    r = client.post(f"{pub(c)}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"],
                                             "start_at": iso(ist(c.monday, hour)), "session_key": key})
    assert r.status_code == 201, r.text
    return r.json()


def policy(client, c: Clinic, **values):
    r = client.put(f"/api/v1/organizations/{c.org['id']}/settings/otp", json={"values": values}, headers=c.h)
    assert r.status_code == 200, r.text
    return r.json()["values"]


def start(client, c: Clinic, h: dict, channel="sms", destination=MOBILE, key="otp-session-1", expect=200):
    r = client.post(f"{pub(c)}/verification/start", json={"channel": channel, "destination": destination, "hold_id": h["id"], "session_key": key})
    assert r.status_code == expect, r.text
    return r.json()


def last_code(client, destination: str) -> str:
    r = client.get("/api/v1/dev/outbox/latest-code", params={"destination": destination})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def verify(client, c: Clinic, challenge_id: str, code: str, key="otp-session-1"):
    return client.post(f"{pub(c)}/verification/{challenge_id}/verify", json={"code": code, "session_key": key})


def book(client, c: Clinic, h: dict, token: str | None, mobile: str | None = MOBILE, email: str | None = None, key="otp-session-1", headers=None):
    customer = {"full_name": "Asha Patel", **({"mobile": mobile} if mobile else {}), **({"email": email} if email else {})}
    return client.post(f"{pub(c)}/appointments", headers=headers, json={"hold_id": h["id"], "session_key": key, "verification_token": token, "customer": customer})


def verified_token(client, c: Clinic, h: dict, channel="sms", destination=MOBILE, key="otp-session-1") -> str:
    ch = start(client, c, h, channel, destination, key)
    target = E164 if channel != "email" and destination == MOBILE else destination
    r = verify(client, c, ch["challenge_id"], last_code(client, target), key)
    assert r.status_code == 200, r.text
    return r.json()["verification_token"]


# ------------------------------------------------------------------------------------------------ defaults and flow
def test_new_clinic_requires_a_code_and_offers_sms(client, clinic):
    opts = client.get(f"{pub(clinic)}/verification").json()
    assert opts == {"required": True, "channels": ["sms"], "default_channel": "sms", "code_length": 6, "resend_cooldown_seconds": 60}


def test_booking_api_cannot_be_called_without_verification(client, clinic):
    h = hold(client, clinic)
    r = book(client, clinic, h, None)
    assert r.status_code == 422 and r.json()["code"] == "contact_not_verified"
    assert book(client, clinic, h, "not-a-token").json()["code"] == "contact_not_verified"


def test_sms_flow_never_returns_the_code_and_each_code_works_once(client, clinic):
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    assert set(ch) == {"challenge_id", "channel", "destination", "code_length", "expires_in_seconds", "resend_after_seconds", "resends_left"}
    assert ch["destination"] == "+91•••••001" and ch["resend_after_seconds"] > 50 and ch["resends_left"] == 3
    code = last_code(client, E164)
    assert code not in json.dumps(ch)
    message = console_provider("sms").outbox[-1]
    assert message.sensitive and code in message.body and message.template_params == [code, "5"]
    r = verify(client, clinic, ch["challenge_id"], code)
    assert r.status_code == 200 and r.json()["channel"] == "sms" and r.json()["destination"] == E164
    assert verify(client, clinic, ch["challenge_id"], code).json()["code"] == "otp_used"
    r = book(client, clinic, h, r.json()["verification_token"])
    assert r.status_code == 201, r.text


def test_code_is_stored_only_as_a_hash(client, clinic, db):
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    code = last_code(client, E164)
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == ch["challenge_id"]))
    assert code not in row.code_hash and len(row.code_hash) == 64 and row.delivery_status == "sent"


def test_email_and_whatsapp_channels(client, clinic):
    policy(client, clinic, channels=["whatsapp", "sms", "email"], default_channel="whatsapp")
    opts = client.get(f"{pub(clinic)}/verification").json()
    assert opts["channels"] == ["whatsapp", "sms", "email"] and opts["default_channel"] == "whatsapp"

    h = hold(client, clinic)
    token = verified_token(client, clinic, h, "email", EMAIL.upper())  # addresses are compared case-insensitively
    assert console_provider("email").outbox[-1].subject.endswith("Akshar Clinic")
    assert book(client, clinic, h, token, mobile=None, email="someone.else@example.com").json()["code"] == "contact_not_verified"
    assert book(client, clinic, h, token, mobile=MOBILE, email=None).json()["code"] == "contact_not_verified"
    assert book(client, clinic, h, token, mobile=MOBILE, email=EMAIL).status_code == 201

    h2 = hold(client, clinic, hour=10, key="otp-session-2")
    token = verified_token(client, clinic, h2, "whatsapp", MOBILE, key="otp-session-2")
    assert console_provider("whatsapp").outbox[-1].sensitive  # (the Meta copy-code button is checked in the Cloud API test)
    assert book(client, clinic, h2, token, key="otp-session-2").status_code == 201


def test_channels_the_clinic_did_not_enable_are_refused(client, clinic):
    h = hold(client, clinic)
    r = start(client, clinic, h, "email", EMAIL, expect=422)
    assert r["code"] == "otp_channel_unavailable"


# ---------------------------------------------------------------------------------------------- token binding
def test_token_only_works_for_the_verified_contact_hold_session_and_clinic(client, clinic):
    h = hold(client, clinic)
    token = verified_token(client, clinic, h)
    assert book(client, clinic, h, token, mobile="9812300099").json()["code"] == "contact_not_verified"  # someone else's number
    h2 = hold(client, clinic, hour=10, key="otp-session-2")
    assert book(client, clinic, h2, token, key="otp-session-2").json()["code"] == "contact_not_verified"  # another booking
    other = Clinic(client, email="otp-other@example.com", name="Other Clinic", payment_mode="pay_at_clinic", verify_mobile=True)
    h3 = hold(client, other)
    r = client.post(f"{pub(other)}/appointments", json={"hold_id": h3["id"], "session_key": "otp-session-1", "verification_token": token,
                                                         "customer": {"full_name": "Asha", "mobile": MOBILE}})
    assert r.json()["code"] == "contact_not_verified"
    assert book(client, clinic, h, token).status_code == 201


def test_another_session_cannot_use_or_see_a_challenge(client, clinic):
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    code = last_code(client, E164)
    r = verify(client, clinic, ch["challenge_id"], code, key="someone-elses-session")
    assert r.status_code == 404 and r.json()["code"] == "otp_not_found"
    assert start(client, clinic, h, key="someone-elses-session", expect=403)["code"] == "hold_mismatch"


# ------------------------------------------------------------------------------------------------- attempts
def test_wrong_codes_are_counted_even_though_the_request_fails_and_then_lock(client, clinic, db):
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    code = last_code(client, E164)
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = verify(client, clinic, ch["challenge_id"], wrong)
        assert r.status_code == 401 and r.json()["code"] == "otp_incorrect" and f"{left} attempt" in r.json()["detail"]
    assert verify(client, clinic, ch["challenge_id"], wrong).json()["code"] == "otp_locked"
    assert verify(client, clinic, ch["challenge_id"], code).json()["code"] == "otp_locked"  # the right code is too late
    db.expire_all()
    assert db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == ch["challenge_id"])).attempts == 5


def test_expired_and_superseded_codes(client, clinic, db):
    h = hold(client, clinic)
    first = start(client, clinic, h)
    first_code = last_code(client, E164)
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == first["challenge_id"]))
    row.last_sent_at = utcnow() - timedelta(minutes=5)
    db.commit()
    second = start(client, clinic, h)  # a new request replaces the open one
    assert verify(client, clinic, first["challenge_id"], first_code).json()["code"] == "otp_superseded"
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == second["challenge_id"]))
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert verify(client, clinic, second["challenge_id"], last_code(client, E164)).json()["code"] == "otp_expired"


def test_resend_cooldown_new_code_and_cap(client, clinic, db):
    policy(client, clinic, max_resends=2, resend_cooldown_seconds=30)
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    old = last_code(client, E164)
    r = client.post(f"{pub(clinic)}/verification/{ch['challenge_id']}/resend", json={"session_key": "otp-session-1"})
    assert r.status_code == 429 and r.json()["code"] == "otp_cooldown" and r.headers["retry-after"]

    def rewind():
        row = db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == ch["challenge_id"]))
        row.last_sent_at = utcnow() - timedelta(minutes=2)
        db.commit()

    for left in (1, 0):
        rewind()
        r = client.post(f"{pub(clinic)}/verification/{ch['challenge_id']}/resend", json={"session_key": "otp-session-1"})
        assert r.status_code == 200 and r.json()["resends_left"] == left
    rewind()
    r = client.post(f"{pub(clinic)}/verification/{ch['challenge_id']}/resend", json={"session_key": "otp-session-1"})
    assert r.status_code == 429 and r.json()["code"] == "otp_resend_limit"
    new = last_code(client, E164)
    if new != old:
        assert verify(client, clinic, ch["challenge_id"], old).json()["code"] == "otp_incorrect"  # the resent code replaced it
    assert verify(client, clinic, ch["challenge_id"], new).status_code == 200


# -------------------------------------------------------------------------------------------------- limits
def test_limits_per_destination_session_and_across_clinics(client, clinic, db):
    policy(client, clinic, limit_per_destination_hour=2, limit_per_session_hour=3)
    h = hold(client, clinic)
    start(client, clinic, h)
    start(client, clinic, h)
    assert start(client, clinic, h, expect=429)["code"] == "otp_destination_limit"
    start(client, clinic, h, destination="9812300002")  # another number: fine, until the session cap
    assert start(client, clinic, h, destination="9812300003", expect=429)["code"] == "otp_session_limit"

    # The same number cannot be flooded through many clinics either (10 codes per hour across the platform).
    for row in db.scalars(select(OtpChallenge)):
        row.resend_count = 4
    db.commit()
    other = Clinic(client, email="otp-flood@example.com", name="Flood Clinic", payment_mode="pay_at_clinic", verify_mobile=True)
    assert start(client, other, hold(client, other), expect=429)["code"] == "otp_destination_limit"


def test_per_ip_route_limit(client, clinic):
    h = hold(client, clinic)
    limiter.enabled = True
    limiter.reset()
    try:
        statuses = [client.post(f"{pub(clinic)}/verification/start", json={"channel": "sms", "destination": f"98123100{i:02d}", "hold_id": h["id"],
                                                                            "session_key": f"otp-ip-session-{i}"}).status_code for i in range(6)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert statuses[5] == 429


def test_delivery_failure_is_reported_without_leaking_details(client, clinic, db):
    console_provider("sms").fail_next.append(DeliveryResult("console", False, error="HTTP 400: invalid number 123456"))
    h = hold(client, clinic)
    r = start(client, clinic, h, expect=503)
    assert r["code"] == "otp_delivery_failed" and "SMS" in r["detail"] and "HTTP" not in r["detail"]
    row = db.scalar(select(OtpChallenge).order_by(OtpChallenge.id.desc()))
    assert row.delivery_status == "failed"  # recorded even though the request failed, so it counts towards limits


def test_codes_never_reach_the_logs(client, clinic, monkeypatch):
    seen = []
    monkeypatch.setattr(P.log, "info", lambda event, **kw: seen.append(json.dumps({"event": event, **kw}, default=str)))
    h = hold(client, clinic)
    start(client, clinic, h)
    code = last_code(client, E164)
    assert seen and all(code not in line for line in seen)


# ----------------------------------------------------------------------------------------- signed-in / staff
def test_signed_in_customer_with_a_verified_mobile_skips_the_code(client, clinic):
    user = otp_login(client, MOBILE, "Asha Patel")
    client.cookies.clear()
    h = hold(client, clinic)
    assert book(client, clinic, h, None, headers=bearer(user)).status_code == 201
    h2 = hold(client, clinic, hour=10, key="otp-session-2")
    assert book(client, clinic, h2, None, mobile="9812300077", key="otp-session-2", headers=bearer(user)).json()["code"] == "contact_not_verified"


def test_staff_bookings_and_switched_off_verification(client, clinic):
    assert clinic.staff_book(ist(clinic.monday, 9))["status"] in ("confirmed", "pending_payment")
    policy(client, clinic, required_for_booking=False)
    assert client.get(f"{pub(clinic)}/verification").json()["required"] is False
    assert book(client, clinic, hold(client, clinic, hour=10), None).status_code == 201


# -------------------------------------------------------------------------------------------------- policy
@pytest.mark.parametrize("values", [
    {"code_length": 5}, {"code_length": 3}, {"expiry_seconds": 10}, {"max_attempts": 50}, {"channels": []}, {"channels": ["sms", "fax"]},
    {"channels": ["sms"], "default_channel": "email"}, {"enabled": "yes"}, {"limit_per_ip_hour": True},
])
def test_policy_values_are_validated(client, clinic, values):
    r = client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/otp", json={"values": values}, headers=clinic.h)
    assert r.status_code == 422 and r.json()["code"] == "invalid_otp_setting", r.text


def test_four_digit_codes(client, clinic):
    policy(client, clinic, code_length=4)
    h = hold(client, clinic)
    ch = start(client, clinic, h)
    assert ch["code_length"] == 4 and len(last_code(client, E164)) == 4


def test_only_admins_manage_verification(client, clinic):
    from tests.test_payments import _verifier

    rec = _verifier(client, clinic, role="receptionist", mobile="9600000901")
    assert client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/otp", json={"values": {"required_for_booking": False}}, headers=rec).status_code == 403
    assert client.put("/api/v1/verification/providers/sms", json={"provider": "msg91", "settings": {}}, headers=rec).status_code == 403


# ----------------------------------------------------------------------------------------- clinic accounts
_REAL_CLIENT = httpx.Client


def _mock_http(monkeypatch, handler):
    monkeypatch.setattr(P.httpx, "Client", lambda *a, **k: _REAL_CLIENT(transport=httpx.MockTransport(handler)))


def test_clinic_msg91_account_secrets_encrypted_and_exact_request(client, clinic, db, monkeypatch):
    r = client.put("/api/v1/verification/providers/sms", headers=clinic.h, json={
        "provider": "msg91", "settings": {"sender_id": "AKSHAR", "template_id": "6650flow"}, "secrets": {"auth_key": "msg91-secret-key-12345"}})
    assert r.status_code == 200, r.text
    assert "msg91-secret-key-12345" not in r.text
    sms = next(c for c in r.json()["channels"] if c["channel"] == "sms")
    assert sms["using"] == "clinic" and sms["own"]["secret_hints"] == {"auth_key": "…2345"} and sms["own"]["secrets_set"] == ["auth_key"]
    row = db.scalar(select(MessagingProviderConfig).where(MessagingProviderConfig.channel == "sms"))
    assert "msg91-secret-key-12345" not in (row.secrets_encrypted or "") and row.secrets_encrypted.startswith("enc:")

    # Saving again without the secret keeps it.
    client.put("/api/v1/verification/providers/sms", headers=clinic.h, json={"provider": "msg91", "settings": {"sender_id": "AKSHAR", "template_id": "6650flow"}})
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"type": "success", "message": "req-1"})

    _mock_http(monkeypatch, handler)
    h = hold(client, clinic)
    start(client, clinic, h)
    req = seen[-1]
    body = json.loads(req.content)
    assert str(req.url) == "https://control.msg91.com/api/v5/flow/" and req.headers["authkey"] == "msg91-secret-key-12345"
    assert body["template_id"] == "6650flow" and body["sender"] == "AKSHAR" and body["recipients"][0]["mobiles"] == "919812300001"
    code = body["recipients"][0]["var1"]
    assert len(code) == 6 and body["recipients"][0]["var2"] == "5"
    assert verify(client, clinic, start(client, clinic, h, destination="9812300002")["challenge_id"], json.loads(seen[-1].content)["recipients"][0]["var1"]).status_code == 200

    # The admin test button sends a sample and records the outcome; provider errors are shown without secrets.
    def failing(req):
        return httpx.Response(401, json={"type": "error", "message": "Authentication failure"})

    _mock_http(monkeypatch, failing)
    r = client.post("/api/v1/verification/providers/sms/test", json={"destination": "9812300050"}, headers=clinic.h)
    assert r.status_code == 200 and r.json()["ok"] is False and "401" in r.json()["error"]
    sms = next(c for c in client.get("/api/v1/verification", headers=clinic.h).json()["channels"] if c["channel"] == "sms")
    assert sms["own"]["last_test_ok"] is False


def test_clinic_whatsapp_cloud_api_request_uses_the_authentication_template(client, clinic, monkeypatch):
    r = client.put("/api/v1/verification/providers/whatsapp", headers=clinic.h, json={
        "provider": "meta", "settings": {"phone_number_id": "1098765", "template_name": "akshar_otp", "language": "en_US"}, "secrets": {"access_token": "EAAG-token"}})
    assert r.status_code == 200, r.text
    policy(client, clinic, channels=["whatsapp", "sms"], default_channel="whatsapp")
    seen: list[httpx.Request] = []
    _mock_http(monkeypatch, lambda req: (seen.append(req), httpx.Response(200, json={"messages": [{"id": "wamid.1"}]}))[1])
    h = hold(client, clinic)
    ch = start(client, clinic, h, "whatsapp")
    req = seen[-1]
    body = json.loads(req.content)
    assert str(req.url).endswith("/1098765/messages") and req.headers["authorization"] == "Bearer EAAG-token"
    template = body["template"]
    assert template["name"] == "akshar_otp" and template["language"] == {"code": "en_US"}
    code = template["components"][0]["parameters"][0]["text"]
    assert template["components"][1] == {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]}
    assert verify(client, clinic, ch["challenge_id"], code).status_code == 200


def test_clinic_smtp_account_sends_the_clinic_template(client, clinic, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            self.host, self.port = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            pass

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, msg):
            sent.append(msg)
            return {}

    monkeypatch.setattr(P.smtplib, "SMTP", FakeSMTP)
    r = client.put("/api/v1/verification/providers/email", headers=clinic.h, json={"provider": "smtp", "settings": {
        "host": "smtp.akshar.example", "port": "587", "security": "starttls", "username": "otp@akshar.example", "from_email": "otp@akshar.example",
        "from_name": "Akshar Clinic", "subject": "Your Akshar code", "template": "Namaste! Your code is {{code}} ({{minutes}} min)."}, "secrets": {"password": "smtp-pass"}})
    assert r.status_code == 200, r.text
    policy(client, clinic, channels=["sms", "email"])
    h = hold(client, clinic)
    ch = start(client, clinic, h, "email", EMAIL)
    msg = sent[-1]
    assert ("login", "otp@akshar.example", "smtp-pass") in sent and msg["Subject"] == "Your Akshar code" and msg["To"] == EMAIL
    text = msg.get_body(("plain",)).get_content()
    code = text.split("Your code is ")[1][:6]
    assert "(5 min)" in text and verify(client, clinic, ch["challenge_id"], code).status_code == 200


def test_incomplete_or_invalid_accounts_are_refused(client, clinic):
    r = client.put("/api/v1/verification/providers/sms", headers=clinic.h, json={"provider": "msg91", "settings": {"sender_id": "AKSHAR"}})
    assert r.status_code == 422 and r.json()["code"] == "provider_incomplete" and "Auth key" in r.json()["detail"]
    r = client.put("/api/v1/verification/providers/sms", headers=clinic.h, json={"provider": "smtp", "settings": {}})
    assert r.json()["code"] == "invalid_provider"
    r = client.put("/api/v1/verification/providers/email", headers=clinic.h, json={"provider": "smtp", "enabled": False, "settings": {"template": "no code here"}})
    assert r.json()["code"] == "invalid_provider_setting"
    # A disabled clinic account falls back to the platform; removing it does too.
    r = client.put("/api/v1/verification/providers/sms", headers=clinic.h, json={"provider": "msg91", "enabled": False, "settings": {"sender_id": "AKSHAR"}})
    assert r.status_code == 200 and next(c for c in r.json()["channels"] if c["channel"] == "sms")["using"] == "platform"
    assert client.delete("/api/v1/verification/providers/sms", headers=clinic.h).status_code == 200
