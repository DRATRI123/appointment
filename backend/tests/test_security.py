"""Phase 12 security regression tests.

Each test pins down a specific attack or failure mode so a later refactor cannot silently reopen it:
tenant isolation across every ID-taking route, token tampering, CSRF, persistence of security counters when the
request itself fails, forwarded-IP spoofing, mass assignment, and information leaks in error responses.
"""
from __future__ import annotations

import io
import re
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from app.core.config import get_settings
from app.core.time import utcnow
from app.main import create_app
from app.models import (
    BankTransaction,
    Integration,
    Notification,
    OTPVerification,
    PaymentSubmission,
    User,
    UserSession,
    WebhookEvent,
)
from app.security import api_keys as ak
from app.security.client_ip import client_ip
from tests.booking_helpers import Clinic
from tests.helpers import PASSWORD, bearer, register
from tests.test_payments import PNG, _account, _booked, _storage, _submit, _verifier
from tests.test_refunds_reconciliation import _import, _statement

# ----------------------------------------------------------------------------------------------- tenant isolation
# Path parameters that are not tenant-owned identifiers (or are covered elsewhere) are not swept.
NOT_TENANT_IDS = {"slug", "token", "key", "namespace"}
# Routes where even the owner legitimately gets 403/404 with the seeded data (the sanity check below skips them).
OWNER_MAY_FAIL = {
    "/api/v1/refunds/{refund_id}/proof",  # no proof file has been uploaded for the seeded refund
}
FILLERS = {"namespace": "booking", "slug": "x", "token": "x", "key": "x"}


def _seed_everything(client, db, c: Clinic) -> dict[str, str]:
    """Create one of every tenant-owned resource in clinic ``c`` and return {path_param_name: public_id}."""
    ids: dict[str, str] = {
        "organization_id": c.org["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "professional_id": c.pro["id"],
    }
    ids["account_id"] = _account(c)["id"]
    appt = _booked(c, hour=9, mobile="9711111111")
    ids["appointment_id"] = appt["id"]
    payment = _submit(client, c, appt, utr="612345678901", screenshot=PNG)["payment"]
    ids["payment_id"] = payment["id"]
    ids["submission_id"] = db.scalars(select(PaymentSubmission.public_id).order_by(PaymentSubmission.id.desc())).first()

    acc = _verifier(client, c, mobile="9600000091")
    r = client.post(f"/api/v1/admin/payments/{payment['id']}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000}, headers=acc)
    assert r.status_code == 200, r.text
    ids["refund_id"] = c.post("/refunds", {"payment_id": payment["id"], "amount_paise": 1000, "reason": "Sweep"})["id"]

    customer_id = c.get("/customers")["data"][0]["id"]
    ids["customer_id"] = customer_id
    c.post(f"/customers/{customer_id}/notes", {"body": "Private clinical note", "note_type": "general"})
    r = client.post(f"/api/v1/customers/{customer_id}/documents", files={"file": ("r.png", io.BytesIO(PNG), "image/png")},
                    data={"title": "Report", "document_type": "report"}, headers=c.h)
    assert r.status_code == 201, r.text
    ids["document_id"] = r.json()["id"]
    ids["form_id"] = c.post("/booking-forms", {"name": "Skin", "scope": "service", "clone_from": "template-skin-consultation"})["id"]

    _import(client, acc, _statement([("UPI-SWEEP-612345678901-PAY", "0000612345678901", "", "500.00")]))
    # Bank transactions are addressed by their integer key; lookups are still scoped to the organization.
    ids["txn_id"] = str(db.scalars(select(BankTransaction.id).where(BankTransaction.organization_id == _org_pk(db, c))).first())
    ids["notification_id"] = db.scalars(select(Notification.public_id).where(Notification.organization_id == _org_pk(db, c))).first()

    integ = Integration(organization_id=_org_pk(db, c), provider="zoom", name="Zoom", status="connected")
    db.add(integ)
    db.flush()
    ids["integration_id"] = integ.public_id

    ids["key_id"] = c.post("/developers/api-keys", {"name": "Sweep", "scopes": ["appointments:read"]})["id"]
    endpoint = c.post("/developers/webhooks", {"name": "Sweep", "url": "https://hooks.example.com/sweep", "events": ["*"]})
    ids["endpoint_id"] = endpoint["id"]
    c.staff_book(_slot(c, 10), customer={"full_name": "Hook Trigger", "mobile": "9711111112"})
    ids["delivery_id"] = db.scalars(select(WebhookEvent.public_id).order_by(WebhookEvent.id.desc())).first()
    assert all(ids.values()), {k: v for k, v in ids.items() if not v}
    return ids


def _slot(c: Clinic, hour: int):
    from tests.booking_helpers import ist

    return ist(c.monday, hour)


def _org_pk(db, c: Clinic) -> int:
    from app.models import Organization

    return db.scalars(select(Organization.id).where(Organization.public_id == c.org["id"])).one()


def _tenant_get_routes() -> list[str]:
    schema = create_app().openapi()
    routes = []
    for path, ops in schema["paths"].items():
        if "get" not in ops or "{" not in path or path.startswith(("/api/v1/public/", "/api/v1/platform/")):
            continue
        if set(re.findall(r"{(\w+)}", path)) <= NOT_TENANT_IDS:
            continue
        routes.append(path)
    return routes


def test_every_id_route_refuses_another_tenants_resources(client, db, tmp_path):
    """Generated from the OpenAPI schema, so a newly added GET route with an ID is covered automatically."""
    storage_module = _storage(tmp_path)
    ak.limiter.reset()
    try:
        a = Clinic(client, email="idor-a@example.com", name="Alpha Clinic")
        ids = _seed_everything(client, db, a)
        b = Clinic(client, email="idor-b@example.com", name="Bravo Clinic")

        routes = _tenant_get_routes()
        assert len(routes) >= 35, routes
        leaks, unswept = [], []
        for route in routes:
            params = set(re.findall(r"{(\w+)}", route)) - NOT_TENANT_IDS
            if not params <= ids.keys():
                unswept.append(route)
                continue
            path = route
            for name in re.findall(r"{(\w+)}", route):
                path = path.replace("{" + name + "}", ids.get(name) or FILLERS[name])
            # Bravo's owner, acting in Bravo, asks for Alpha's resource by ID.
            r = client.get(path, headers=b.h)
            if route.startswith("/api/v1/customer/") and r.status_code == 200 and r.json() == []:
                continue  # the caller's own (empty) list at that clinic; nothing of Alpha's is returned
            if r.status_code not in (401, 403, 404, 422):
                leaks.append((route, r.status_code))
            elif any(len(v) > 8 and v in r.text for v in ids.values()):
                leaks.append((route, "id echoed in error"))
            # Sanity check: the same request as Alpha's owner is not refused for ownership reasons.
            if "/customer/" not in route and route not in OWNER_MAY_FAIL:  # /customer/* is for the patient's own account
                assert client.get(path, headers=a.h).status_code not in (403, 404), route
        assert leaks == []
        # Every ID-taking route must be swept; add a seed above when a new kind of resource appears.
        assert unswept == []

        # Pointing the tenant header at Alpha does not help Bravo either.
        spoofed = {**b.h, "X-Organization-Id": a.org["id"]}
        for path in ("/api/v1/customers", "/api/v1/appointments", "/api/v1/payments", "/api/v1/refunds", "/api/v1/developers/api-keys"):
            assert client.get(path, headers=spoofed).status_code == 403, path
        # Nor does writing to Alpha's objects from Bravo.
        assert client.patch(f"/api/v1/customers/{ids['customer_id']}", json={"full_name": "Hijacked"}, headers=b.h).status_code == 404
        assert client.post(f"/api/v1/admin/payments/{ids['payment_id']}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 1}, headers=b.h).status_code == 404
        assert client.delete(f"/api/v1/developers/api-keys/{ids['key_id']}", headers=b.h).status_code == 404
        # Browsing Alpha's patient routes did not plant Bravo's owner in Alpha's customer list.
        assert all(row["email"] != "idor-b@example.com" for row in a.get("/customers")["data"])
    finally:
        storage_module._storage = None
        ak.limiter.reset()


# ----------------------------------------------------------------------------------------------- tokens
def _claims(client, tokens) -> dict:
    return jwt.decode(tokens["access_token"], options={"verify_signature": False})


@pytest.mark.parametrize("case", ["alg_none", "wrong_key", "expired", "refresh_typ", "garbage"])
def test_tampered_access_tokens_are_rejected(client, case):
    tokens = register(client, f"jwt-{case}@example.com")
    client.cookies.clear()
    claims = _claims(client, tokens)
    settings = get_settings()
    if case == "alg_none":
        token = jwt.encode({**claims, "sub": claims["sub"]}, key="", algorithm="none")
    elif case == "wrong_key":
        token = jwt.encode(claims, "x" * 48, algorithm="HS256")
    elif case == "expired":
        token = jwt.encode({**claims, "exp": int((utcnow() - timedelta(minutes=1)).timestamp())}, settings.secret_key, algorithm=settings.jwt_algorithm)
    elif case == "refresh_typ":
        token = jwt.encode({**claims, "typ": "refresh"}, settings.secret_key, algorithm=settings.jwt_algorithm)
    else:
        token = "not.a.jwt"
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["code"] in ("token_invalid", "token_expired")


def test_token_for_another_user_signed_correctly_still_needs_a_live_session(client):
    """Even a validly signed token is useless once its session is revoked or if it names a session of someone else."""
    victim = register(client, "victim@example.com")
    client.cookies.clear()
    attacker = register(client, "attacker@example.com")
    client.cookies.clear()
    settings = get_settings()
    forged = {**_claims(client, attacker), "sub": _claims(client, victim)["sub"]}
    token = jwt.encode(forged, settings.secret_key, algorithm=settings.jwt_algorithm)
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ----------------------------------------------------------------------------------------------- CSRF
def test_csrf_token_must_match_cookie(client):
    register(client, "csrf2@example.com")
    for header in ({"X-CSRF-Token": "forged"}, {"X-CSRF-Token": ""}, {}):
        r = client.patch("/api/v1/users/me", json={"full_name": "Changed"}, headers=header)
        assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    # Logout deliberately works without the header (a user with a broken session must always be able to sign out);
    # a forged logout is harmless and SameSite=Lax cookies already stop cross-site POSTs.


# ----------------------------------------------------------------------------------------------- persistence on error
def test_security_counters_survive_the_failing_request(client, db):
    """These requests all end in an error response; the bookkeeping they record must still be committed."""
    register(client, "persist@example.com")
    client.cookies.clear()
    for _ in range(2):
        assert client.post("/api/v1/auth/login", json={"email": "persist@example.com", "password": "wrong-pass1"}).status_code == 401
    db.expire_all()
    user = db.scalars(select(User).where(User.email == "persist@example.com")).one()
    assert user.failed_login_attempts == 2
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": "persist@example.com", "password": "wrong-pass1"})
    db.expire_all()
    assert user.locked_until is not None

    code = client.post("/api/v1/auth/otp/request", json={"identifier": "9000000077"}).json()["debug_code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/v1/auth/otp/verify", json={"identifier": "9000000077", "code": wrong}).status_code == 401
    db.expire_all()
    otp = db.scalars(select(OTPVerification).order_by(OTPVerification.id.desc())).first()
    assert otp.attempts == 1

    tokens = register(client, "reuse@example.com")
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    db.expire_all()
    owner = db.scalars(select(User).where(User.email == "reuse@example.com")).one()
    sessions = db.scalars(select(UserSession).where(UserSession.user_id == owner.id)).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)


def test_successful_login_after_failures_resets_the_counter(client, db):
    register(client, "reset-count@example.com")
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "reset-count@example.com", "password": "wrong-pass1"})
    assert client.post("/api/v1/auth/login", json={"email": "reset-count@example.com", "password": PASSWORD}).status_code == 200
    db.expire_all()
    assert db.scalars(select(User).where(User.email == "reset-count@example.com")).one().failed_login_attempts == 0


def test_unrelated_errors_still_roll_back(client, db):
    """persist is opt-in: an ordinary failure must not commit half-done work."""
    c = Clinic(client, email="rollback@example.com", name="Rollback Clinic")
    before = c.get("/services")["meta"]["total"] if isinstance(c.get("/services"), dict) else len(c.get("/services"))
    r = client.post("/api/v1/services", json={"name": "Bad", "duration_minutes": 30, "price_paise": -5}, headers=c.h)
    assert r.status_code == 422
    after = c.get("/services")
    assert (after["meta"]["total"] if isinstance(after, dict) else len(after)) == before


# ----------------------------------------------------------------------------------------------- client IP
def _request(peer: str, xff: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234), "method": "GET", "path": "/"})


def test_client_ip_cannot_be_spoofed_through_forwarded_for(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "forwarded_allow_ips", ["10.0.0.0/8"])
    # Untrusted peer: header ignored.
    assert client_ip(_request("203.0.113.9", "1.1.1.1")) == "203.0.113.9"
    # Trusted proxy appended the real address after the client's forged one: the forged entry is ignored.
    assert client_ip(_request("10.0.0.2", "198.51.100.7, 203.0.113.9")) == "203.0.113.9"
    # Several of our own proxies in a row are skipped.
    assert client_ip(_request("10.0.0.2", "203.0.113.9, 10.0.0.5")) == "203.0.113.9"
    # Garbage in the chain is not trusted.
    assert client_ip(_request("10.0.0.2", "evil\r\nX: 1")) == "10.0.0.2"
    assert client_ip(_request("10.0.0.2", "203.0.113.9, not-an-ip")) == "10.0.0.2"
    assert client_ip(_request("10.0.0.2", None)) == "10.0.0.2"


# ----------------------------------------------------------------------------------------------- mass assignment
def test_privileged_fields_cannot_be_set_by_users(client, db):
    r = client.post("/api/v1/auth/register", json={"full_name": "Sneaky", "email": "sneaky@example.com", "password": PASSWORD,
                                                   "is_platform_admin": True, "status": "active", "email_verified_at": "2020-01-01T00:00:00Z"})
    assert r.status_code == 201
    h = bearer(r.json())
    client.cookies.clear()
    client.patch("/api/v1/users/me", json={"full_name": "Sneaky", "is_platform_admin": True, "failed_login_attempts": -100}, headers=h)
    db.expire_all()
    user = db.scalars(select(User).where(User.email == "sneaky@example.com")).one()
    assert user.is_platform_admin is False and user.email_verified_at is None and user.failed_login_attempts == 0
    assert client.get("/api/v1/platform/stats", headers=h).status_code == 403


def test_payment_amount_cannot_be_chosen_by_the_customer(client, tmp_path):
    """Payable amounts come from the service price on the backend; extra fields in the submission are ignored."""
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="amount@example.com", name="Amount Clinic")
        _account(c)
        appt = _booked(c, hour=9, mobile="9722222222")
        r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment/submit",
                        params={"access_token": appt["access_token"]}, data={"utr": "712345678901", "amount_paise": "1", "status": "verified"})
        assert r.status_code == 200, r.text
        payment = r.json()["payment"]
        assert payment["amount_paise"] == 50000 and payment["status"] in ("submitted", "under_review")
    finally:
        storage_module._storage = None


# ----------------------------------------------------------------------------------------------- responses
def test_api_responses_carry_security_headers(client):
    for r in (client.get("/api/v1/health"), client.get("/api/v1/does-not-exist"), client.post("/api/v1/auth/login", json={})):
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "server" not in {k.lower() for k in r.headers if r.headers[k].lower().startswith("uvicorn")}


def test_validation_errors_do_not_echo_submitted_values(client):
    secret = "tiny"  # fails the password policy
    r = client.post("/api/v1/auth/register", json={"full_name": "Echo", "email": "echo@example.com", "password": secret})
    assert r.status_code == 422
    assert secret not in r.text
    r = client.post("/api/v1/auth/otp/verify", json={"identifier": "9000000078", "code": "12x"})
    assert r.status_code == 422 and "12x" not in r.text


def test_unexpected_errors_return_a_generic_message_with_request_id():
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_error" and "hunter2" not in r.text and body.get("request_id")


def test_request_id_header_is_sanitised(client):
    good = client.get("/api/v1/health", headers={"X-Request-ID": "trace-1234abcd"})
    assert good.headers["X-Request-ID"] == "trace-1234abcd"
    bad = client.get("/api/v1/health", headers={"X-Request-ID": "x" * 500})
    assert bad.headers["X-Request-ID"] != "x" * 500 and re.fullmatch(r"[0-9a-f]{32}", bad.headers["X-Request-ID"])
    forged = client.get("/api/v1/health", headers={"X-Request-ID": 'abc" level=critical msg="forged'})
    assert re.fullmatch(r"[0-9a-f]{32}", forged.headers["X-Request-ID"])


def test_media_mount_does_not_serve_private_files(client, tmp_path):
    """Only storage/public is mounted; private uploads (screenshots, documents) are never reachable by path."""
    for path in ("/media/../private/x.png", "/media/%2e%2e/private/x.png", "/media/..%2fprivate/x.png"):
        assert client.get(path).status_code == 404
