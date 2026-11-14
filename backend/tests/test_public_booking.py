"""Public booking page backend: mobile verification by one-time code, embed policy, reserved web addresses, and
server-side trust (prices and authorization never come from the URL or the browser)."""
from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.time import utcnow
from app.security.rate_limit import limiter
from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, create_org, otp_login, register

MOBILE = "9812300001"


def _public(c: Clinic) -> str:
    return f"/api/v1/public/organizations/{c.org['slug']}"


def _hold(client, c: Clinic, hour: int = 9, key: str = "pb-session-1") -> dict:
    r = client.post(f"{_public(c)}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"],
                                                  "start_at": iso(ist(c.monday, hour)), "session_key": key})
    assert r.status_code == 201, r.text
    return r.json()


def _send(client, c: Clinic, hold: dict, mobile: str = MOBILE, key: str = "pb-session-1", expect: int = 200) -> dict:
    r = client.post(f"{_public(c)}/verify-mobile", json={"mobile": mobile, "hold_id": hold["id"], "session_key": key})
    assert r.status_code == expect, r.text
    return r.json()


def _confirm(client, c: Clinic, hold: dict, code: str, mobile: str = MOBILE, key: str = "pb-session-1"):
    return client.post(f"{_public(c)}/verify-mobile/confirm", json={"mobile": mobile, "code": code, "hold_id": hold["id"], "session_key": key})


def _book(client, c: Clinic, hold: dict, token: str | None, mobile: str = MOBILE, key: str = "pb-session-1", **extra):
    return client.post(f"{_public(c)}/appointments", json={"hold_id": hold["id"], "session_key": key, "mobile_verification_token": token,
                                                           "customer": {"full_name": "Asha Patel", "mobile": mobile}, **extra})


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="pb-owner@example.com", name="Akshar Clinic", payment_mode="pay_at_clinic", verify_mobile=True)


# ------------------------------------------------------------------------------------------------- mobile codes
def test_new_clinics_require_a_verified_mobile_for_online_bookings(client):
    tokens = register(client, "fresh-owner@example.com")
    client.cookies.clear()
    org = create_org(client, bearer(tokens), "Fresh Clinic")
    r = client.get(f"/api/v1/organizations/{org['id']}/settings/booking", headers={**bearer(tokens), "X-Organization-Id": org["id"]})
    assert r.json()["values"]["require_mobile_verification"] is True


def test_booking_without_a_verified_mobile_is_refused(client, clinic):
    hold = _hold(client, clinic)
    r = _book(client, clinic, hold, None)
    assert r.status_code == 422 and r.json()["code"] == "mobile_not_verified"
    r = client.post(f"{_public(clinic)}/appointments", json={"hold_id": hold["id"], "session_key": "pb-session-1", "customer": {"full_name": "No Phone", "email": "a@example.com"}})
    assert r.status_code == 422 and r.json()["code"] == "mobile_required"


def test_full_flow_code_then_booking(client, clinic):
    hold = _hold(client, clinic)
    sent = _send(client, clinic, hold)
    assert sent["debug_code"] and sent["resend_after_seconds"] > 0
    r = _confirm(client, clinic, hold, sent["debug_code"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mobile"] == "+919812300001" and body["expires_in_seconds"] == 1800
    assert _confirm(client, clinic, hold, sent["debug_code"]).json()["code"] == "otp_not_found"  # a code works once
    r = _book(client, clinic, hold, body["verification_token"])
    assert r.status_code == 201, r.text
    assert r.json()["customer"]["mobile"] == "+919812300001"


def test_token_is_bound_to_the_hold_the_number_and_the_clinic(client, clinic):
    hold = _hold(client, clinic)
    token = _confirm(client, clinic, hold, _send(client, clinic, hold)["debug_code"]).json()["verification_token"]
    # Another number on the same booking.
    assert _book(client, clinic, hold, token, mobile="9812300002").json()["code"] == "mobile_not_verified"
    # Another hold.
    other_hold = _hold(client, clinic, hour=10, key="pb-session-2")
    assert _book(client, clinic, other_hold, token, key="pb-session-2").json()["code"] == "mobile_not_verified"
    # A token signed with another key, or edited.
    claims = jwt.decode(token, options={"verify_signature": False})
    assert _book(client, clinic, hold, jwt.encode(claims, "x" * 40, algorithm="HS256")).json()["code"] == "mobile_not_verified"
    assert _book(client, clinic, hold, token[:-4] + "AAAA").json()["code"] == "mobile_not_verified"
    # Expired.
    expired = jwt.encode({**claims, "exp": int((utcnow() - timedelta(minutes=1)).timestamp())}, get_settings().secret_key, algorithm="HS256")
    assert _book(client, clinic, hold, expired).json()["code"] == "mobile_verification_expired"
    # Another clinic cannot use it either.
    other = Clinic(client, email="pb-other@example.com", name="Other Clinic", payment_mode="pay_at_clinic", verify_mobile=True)
    other_hold = _hold(client, other, key="pb-session-3")
    forged = jwt.encode({**claims, "hold": other_hold["id"]}, "wrong-key" * 5, algorithm="HS256")
    assert _book(client, other, other_hold, forged, key="pb-session-3").json()["code"] == "mobile_not_verified"
    assert _book(client, clinic, hold, token).status_code == 201


def test_wrong_codes_are_counted_and_lock_the_code(client, clinic, db):
    from sqlalchemy import select

    from app.models import OTPVerification

    hold = _hold(client, clinic)
    code = _send(client, clinic, hold)["debug_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = _confirm(client, clinic, hold, wrong)
        assert r.status_code == 401 and r.json()["code"] == "otp_incorrect", r.text
    db.expire_all()
    assert db.scalars(select(OTPVerification).order_by(OTPVerification.id.desc())).first().attempts == 5  # saved despite the errors
    assert _confirm(client, clinic, hold, code).json()["code"] == "otp_locked"


def test_codes_need_the_customers_own_live_reservation(client, clinic, db):
    from sqlalchemy import update

    from app.models import BookingHold

    hold = _hold(client, clinic)
    assert _send(client, clinic, hold, key="someone-elses-session", expect=403)["code"] == "hold_mismatch"
    r = client.post(f"{_public(clinic)}/verify-mobile", json={"mobile": MOBILE, "hold_id": "not-a-hold", "session_key": "pb-session-1"})
    assert r.status_code == 422 and r.json()["code"] == "hold_not_found"
    db.execute(update(BookingHold).where(BookingHold.public_id == hold["id"]).values(expires_at=utcnow() - timedelta(minutes=1)))
    assert _send(client, clinic, hold, expect=409)["code"] == "hold_expired"
    assert client.post(f"{_public(clinic)}/verify-mobile", json={"mobile": "12", "hold_id": hold["id"], "session_key": "pb-session-1"}).status_code == 422


def test_resend_cooldown_and_hourly_cap_per_number(client, clinic, monkeypatch):
    hold = _hold(client, clinic)
    _send(client, clinic, hold)
    assert _send(client, clinic, hold, expect=429)["code"] == "otp_cooldown"
    monkeypatch.setattr(get_settings(), "otp_resend_cooldown_seconds", 0)
    for _ in range(4):
        _send(client, clinic, hold)
    assert _send(client, clinic, hold, expect=429)["code"] == "otp_hourly_limit"  # 5 codes per number per hour
    _send(client, clinic, hold, mobile="9812300009")  # a different number is not affected


def test_code_requests_are_rate_limited_per_ip(client, clinic, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_resend_cooldown_seconds", 0)
    hold = _hold(client, clinic)
    limiter.enabled = True
    limiter.reset()
    try:
        statuses = [client.post(f"{_public(clinic)}/verify-mobile",
                                json={"mobile": f"98123100{i:02d}", "hold_id": hold["id"], "session_key": "pb-session-1"}).status_code
                    for i in range(6)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert statuses[:5] == [200] * 5 and statuses[5] == 429


def test_signed_in_customer_with_a_verified_mobile_skips_the_code(client, clinic):
    user = otp_login(client, MOBILE, "Asha Patel")  # verified the number by logging in with it
    client.cookies.clear()
    hold = _hold(client, clinic)
    r = client.post(f"{_public(clinic)}/appointments", headers=bearer(user), json={"hold_id": hold["id"], "session_key": "pb-session-1",
                                                                                  "customer": {"full_name": "Asha Patel", "mobile": MOBILE}})
    assert r.status_code == 201, r.text
    # Booking a different, unverified number still needs the code.
    hold2 = _hold(client, clinic, hour=10, key="pb-session-2")
    r = client.post(f"{_public(clinic)}/appointments", headers=bearer(user), json={"hold_id": hold2["id"], "session_key": "pb-session-2",
                                                                                   "customer": {"full_name": "Asha Patel", "mobile": "9812300077"}})
    assert r.json()["code"] == "mobile_not_verified"


def test_staff_bookings_are_not_affected(client, clinic):
    assert clinic.staff_book(ist(clinic.monday, 9))["status"] in ("confirmed", "pending_payment")


# ---------------------------------------------------------------------------------------- server-side trust
def test_prices_come_from_the_server_never_from_the_request(client):
    c = Clinic(client, email="pb-price@example.com", name="Price Clinic", payment_mode="full_advance", price=80000, verify_mobile=False)
    q = client.get(f"{_public(c)}/quote", params={"service_id": c.service["id"], "branch_id": c.branch["id"], "price_paise": 1, "total_amount_paise": 1})
    assert q.status_code == 200 and q.json()["total_amount_paise"] == 80000
    hold = _hold(client, c)
    r = _book(client, c, hold, None, total_amount_paise=1, advance_due_paise=0, status="confirmed", subtotal_paise=1, source="reception",
              confirm_without_payment=True)
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["total_amount_paise"], body["advance_due_paise"], body["status"], body["source"]) == (80000, 80000, "pending_payment", "online")


def test_unknown_or_inactive_url_parameters_do_not_leak_or_book(client, clinic):
    assert client.get(f"{_public(clinic)}/services/not-a-service").status_code == 404
    assert client.get("/api/v1/public/organizations/no-such-clinic").status_code == 404
    r = client.post(f"{_public(clinic)}/holds", json={"professional_id": clinic.pro["id"], "branch_id": clinic.branch["id"], "service_id": "not-a-service",
                                                      "start_at": iso(ist(clinic.monday, 9)), "session_key": "pb-session-1"})
    assert r.status_code == 404


# --------------------------------------------------------------------------------------------- embedding
def test_embed_policy_is_empty_until_the_clinic_allows_its_website(client, clinic):
    r = client.get(f"{_public(clinic)}/embed-policy")
    assert r.status_code == 200 and r.json() == {"allowed_origins": [], "booking_page_enabled": True}
    assert "max-age=60" in r.headers["cache-control"]
    path = f"/api/v1/organizations/{clinic.org['id']}/settings/embed"
    r = client.put(path, json={"values": {"allowed_origins": ["https://Akshar.myshopify.com/", "https://www.aksharclinic.com", "https://akshar.myshopify.com"]}}, headers=clinic.h)
    assert r.status_code == 200, r.text
    assert client.get(f"{_public(clinic)}/embed-policy").json()["allowed_origins"] == ["https://akshar.myshopify.com", "https://www.aksharclinic.com"]


@pytest.mark.parametrize("bad", ["https://*.myshopify.com", "https://shop.com/pages/book", "javascript:alert(1)", "http://evil.example.com",
                                 "https://a.com https://b.com", "ftp://shop.com", "*", "https://shop.com?x=1"])
def test_embed_origins_must_be_exact_https_addresses(client, clinic, bad):
    r = client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/embed", json={"values": {"allowed_origins": [bad]}}, headers=clinic.h)
    assert r.status_code == 422 and r.json()["code"] == "invalid_embed_origin", (bad, r.text)


def test_only_clinic_admins_can_change_the_embed_policy(client, clinic):
    from tests.test_payments import _verifier

    rec = _verifier(client, clinic, role="receptionist", mobile="9600000701")
    r = client.put(f"/api/v1/organizations/{clinic.org['id']}/settings/embed", json={"values": {"allowed_origins": ["https://evil.example.com"]}}, headers=rec)
    assert r.status_code == 403
    assert client.get(f"{_public(clinic)}/embed-policy").json()["allowed_origins"] == []


# ------------------------------------------------------------------------------------------ web addresses
def test_reserved_web_addresses_cannot_be_taken(client):
    tokens = register(client, "slug-owner@example.com")
    client.cookies.clear()
    r = client.post("/api/v1/organizations", json={"name": "Admin Clinic", "slug": "admin"}, headers=bearer(tokens))
    assert r.status_code == 409 and r.json()["code"] == "slug_reserved"
    org = create_org(client, bearer(tokens), "Embed")  # a name that would slugify to a reserved word gets a suffix
    assert org["slug"] != "embed" and org["slug"].startswith("embed-")
