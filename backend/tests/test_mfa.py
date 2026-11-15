"""Two-step sign-in with an authenticator app, backup codes, lockout, and a clinic requiring it for administrators."""
from __future__ import annotations

import time

from sqlalchemy import select

from app.models import AuditLog, User
from app.security import totp
from app.security.crypto import is_encrypted
from tests.helpers import PASSWORD, bearer, create_org, register


def _login(client, email, password=PASSWORD):
    client.cookies.clear()
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _enable(client, h) -> tuple[str, list[str]]:
    setup = client.post("/api/v1/auth/mfa/setup", headers=h)
    assert setup.status_code == 200, setup.text
    body = setup.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/") and body["qr_data_url"].startswith("data:image/png;base64,")
    secret = body["secret"]
    r = client.post("/api/v1/auth/mfa/enable", json={"code": totp.code_at(secret)}, headers=h)
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def _next_code(secret: str) -> str:
    """A code from the next time step (allowed for clock drift), so it is newer than the one just used."""
    return totp.code_at(secret, time.time() + totp.PERIOD)


def test_rfc6238_reference_values():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
    assert totp.code_at(secret, 59) == "287082"
    assert totp.code_at(secret, 1111111109) == "081804"
    assert totp.verify(secret, "287082", last_step=None, now=59) == 1
    assert totp.verify(secret, "287082", last_step=1, now=59) is None  # never accepted twice


def test_sign_in_needs_the_authenticator_code_once_enabled(client, db):
    h = bearer(register(client, "mfa@example.com", "MFA Owner"))
    secret, codes = _enable(client, h)
    assert len(codes) == 10
    user = db.scalar(select(User).where(User.email == "mfa@example.com"))
    assert is_encrypted(user.mfa_secret) and secret not in user.mfa_secret
    assert all(c not in str(user.mfa_recovery_hashes) for c in codes)

    first = _login(client, "mfa@example.com")
    assert first.status_code == 401 and first.json()["code"] == "mfa_required"
    assert "access_token" not in first.json() and "access_token" not in first.cookies
    token = first.json()["mfa_token"]

    wrong = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "mfa_code_invalid"
    ok = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": _next_code(secret)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["mfa_enabled_at"] is not None
    # The same code cannot be used again (replay).
    again = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": _login(client, "mfa@example.com").json()["mfa_token"], "code": _next_code(secret)})
    assert again.status_code == 401
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_mfa")) is not None


def test_backup_codes_work_once(client):
    h = bearer(register(client, "backup@example.com"))
    _, codes = _enable(client, h)
    token = _login(client, "backup@example.com").json()["mfa_token"]
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codes[0].lower()}).status_code == 200
    token = _login(client, "backup@example.com").json()["mfa_token"]
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codes[0]}).status_code == 401
    status = client.get("/api/v1/auth/mfa", headers=h).json()
    assert status["enabled"] and status["recovery_codes_left"] == 9


def test_wrong_codes_lock_the_account(client):
    h = bearer(register(client, "lock@example.com"))
    secret, _ = _enable(client, h)
    token = _login(client, "lock@example.com").json()["mfa_token"]
    for _ in range(5):
        client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "123456"})
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": _next_code(secret)})
    assert r.status_code == 401 and r.json()["code"] == "account_locked"


def test_tokens_are_not_interchangeable(client):
    tokens = register(client, "swap@example.com")
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": tokens["access_token"], "code": "123456"})
    assert r.status_code == 401 and r.json()["code"] == "mfa_token_invalid"


def test_turning_it_off_needs_password_and_a_code(client):
    h = bearer(register(client, "off@example.com"))
    secret, _ = _enable(client, h)
    assert client.post("/api/v1/auth/mfa/disable", json={"code": _next_code(secret), "password": "wrong-password1"}, headers=h).status_code == 401
    assert client.post("/api/v1/auth/mfa/disable", json={"code": _next_code(secret), "password": PASSWORD}, headers=h).status_code == 200
    assert _login(client, "off@example.com").status_code == 200


def test_a_clinic_can_require_it_for_administrators(client):
    owner = register(client, "owner-mfa@example.com", "Owner")
    h = bearer(owner)
    org = create_org(client, h, "MFA Clinic")
    th = {**h, "X-Organization-Id": org["id"]}
    # The owner cannot lock themselves out: they need it on first.
    r = client.put(f"/api/v1/organizations/{org['id']}/settings/security", json={"values": {"require_admin_mfa": True}}, headers=th)
    assert r.status_code == 422 and r.json()["code"] == "mfa_not_enabled"
    secret, _ = _enable(client, h)
    r = client.put(f"/api/v1/organizations/{org['id']}/settings/security", json={"values": {"require_admin_mfa": True}}, headers=th)
    assert r.status_code == 200, r.text
    # An administrator without it is stopped at the clinic's admin API until they set it up.
    admin = register(client, "admin-mfa@example.com", "Admin")
    client.post(f"/api/v1/organizations/{org['id']}/members", json={"identifier": "admin-mfa@example.com", "full_name": "Admin", "role_code": "org_admin"}, headers=th)
    _login(client, "admin-mfa@example.com")  # signing in accepts the invitation
    ah = {**bearer(admin), "X-Organization-Id": org["id"]}
    blocked = client.get("/api/v1/branches", headers=ah)
    assert blocked.status_code == 403 and blocked.json()["code"] == "mfa_setup_required"
    assert client.get("/api/v1/users/me", headers=bearer(admin)).status_code == 200  # can still reach their profile to set it up
    _enable(client, bearer(admin))
    assert client.get("/api/v1/branches", headers=ah).status_code == 200
    # While the clinic requires it, the owner cannot switch it off for themselves.
    r = client.post("/api/v1/auth/mfa/disable", json={"code": _next_code(secret), "password": PASSWORD}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "mfa_required_by_organization"
