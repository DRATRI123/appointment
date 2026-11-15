"""Public booking page backend: embed policy, reserved web addresses, and server-side trust (prices and authorization
never come from the URL or the browser). One-time-code verification has its own tests in test_otp.py."""
from __future__ import annotations

import pytest

from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, create_org, register

MOBILE = "9812300001"


def _public(c: Clinic) -> str:
    return f"/api/v1/public/organizations/{c.org['slug']}"


def _hold(client, c: Clinic, hour: int = 9, key: str = "pb-session-1") -> dict:
    r = client.post(f"{_public(c)}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"],
                                                  "start_at": iso(ist(c.monday, hour)), "session_key": key})
    assert r.status_code == 201, r.text
    return r.json()


def _book(client, c: Clinic, hold: dict, token: str | None, mobile: str = MOBILE, key: str = "pb-session-1", **extra):
    return client.post(f"{_public(c)}/appointments", json={"hold_id": hold["id"], "session_key": key, "verification_token": token,
                                                           "customer": {"full_name": "Asha Patel", "mobile": mobile}, **extra})


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="pb-owner@example.com", name="Akshar Clinic", payment_mode="pay_at_clinic", verify_mobile=True)


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
