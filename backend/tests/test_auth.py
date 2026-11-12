from __future__ import annotations

from app.security.google import GoogleIdentity, set_google_verifier
from tests.helpers import PASSWORD, bearer, otp_login, register


def test_otp_login_creates_user_and_sets_cookies(client):
    r = client.post("/api/v1/auth/otp/request", json={"identifier": "9876543210"})
    assert r.status_code == 200
    body = r.json()
    assert body["identifier"] == "+919876543210"
    assert body["channel"] == "sms"
    assert body["debug_code"]

    r = client.post("/api/v1/auth/otp/verify", json={"identifier": "98765 43210", "code": body["debug_code"], "full_name": "Asha"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_new_user"] is True
    assert data["user"]["mobile"] == "+919876543210"
    assert data["user"]["mobile_verified_at"] is not None
    assert "access_token" in client.cookies and "refresh_token" in client.cookies and "csrf_token" in client.cookies

    # Second login with the same number is not a new user.
    again = otp_login(client, "+919876543210")
    assert again["is_new_user"] is False


def test_otp_wrong_code_and_attempt_limit(client):
    r = client.post("/api/v1/auth/otp/request", json={"identifier": "9000000001"})
    code = r.json()["debug_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = client.post("/api/v1/auth/otp/verify", json={"identifier": "9000000001", "code": wrong})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/otp/verify", json={"identifier": "9000000001", "code": code})
    assert r.status_code == 401
    assert r.json()["code"] == "otp_locked"


def test_otp_resend_cooldown(client):
    assert client.post("/api/v1/auth/otp/request", json={"identifier": "9000000002"}).status_code == 200
    r = client.post("/api/v1/auth/otp/request", json={"identifier": "9000000002"})
    assert r.status_code == 429
    assert r.json()["code"] == "otp_cooldown"


def test_password_register_login_and_me(client):
    tokens = register(client, "owner@example.com", "Owner One")
    assert tokens["user"]["email"] == "owner@example.com"
    r = client.get("/api/v1/users/me", headers=bearer(tokens))
    assert r.status_code == 200
    assert r.json()["user"]["full_name"] == "Owner One"
    assert r.json()["memberships"] == []

    r = client.post("/api/v1/auth/register", json={"full_name": "Dup", "email": "OWNER@example.com", "password": PASSWORD})
    assert r.status_code == 409

    r = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 200


def test_weak_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"full_name": "Weak", "email": "weak@example.com", "password": "password"})
    assert r.status_code == 422
    assert r.json()["code"] == "weak_password"


def test_account_lockout_after_failed_logins(client):
    register(client, "lock@example.com")
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "wrong-pass1"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["code"] == "account_locked"


def test_cookie_auth_requires_csrf_for_unsafe_methods(client):
    register(client, "csrf@example.com")
    # GET with cookies only: fine.
    assert client.get("/api/v1/users/me").status_code == 200
    # PATCH with cookies but no CSRF header: rejected.
    r = client.patch("/api/v1/users/me", json={"full_name": "Changed"})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"
    # With the double-submit header: accepted.
    r = client.patch("/api/v1/users/me", json={"full_name": "Changed"}, headers={"X-CSRF-Token": client.cookies["csrf_token"]})
    assert r.status_code == 200
    assert r.json()["full_name"] == "Changed"


def test_refresh_rotation_and_reuse_detection(client):
    tokens = register(client, "refresh@example.com")
    client.cookies.clear()
    old_refresh = tokens["refresh_token"]

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != old_refresh
    assert client.get("/api/v1/users/me", headers=bearer(new_tokens)).status_code == 200

    # Replaying the rotated token revokes the whole family.
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401
    assert r.json()["code"] == "refresh_reused"
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 401
    # The access token of the revoked session no longer works either.
    assert client.get("/api/v1/users/me", headers=bearer(new_tokens)).status_code == 401


def test_logout_revokes_session(client):
    tokens = register(client, "logout@example.com")
    r = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies["csrf_token"]})
    assert r.status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401


def test_sessions_list_and_revoke(client):
    first = register(client, "devices@example.com")
    client.cookies.clear()
    second = client.post("/api/v1/auth/login", json={"email": "devices@example.com", "password": PASSWORD, "device_label": "Phone"}).json()
    client.cookies.clear()
    r = client.get("/api/v1/auth/sessions", headers=bearer(second))
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 2
    current = next(s for s in sessions if s["is_current"])
    other = next(s for s in sessions if not s["is_current"])
    assert current["device_label"] == "Phone"
    r = client.delete(f"/api/v1/auth/sessions/{other['id']}", headers=bearer(second))
    assert r.status_code == 200
    assert client.get("/api/v1/users/me", headers=bearer(first)).status_code == 401
    assert client.get("/api/v1/users/me", headers=bearer(second)).status_code == 200


def test_password_reset_flow(client):
    tokens = register(client, "reset@example.com")
    client.cookies.clear()
    r = client.post("/api/v1/auth/password/forgot", json={"email": "reset@example.com"})
    assert r.status_code == 200
    token = r.json()["detail"].split("[debug token: ")[1].rstrip("]")
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "NewPassw0rd!"})
    assert r.status_code == 200
    # token is single use
    assert client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Another1234"}).status_code == 401
    # old sessions revoked, new password works
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "NewPassw0rd!"}).status_code == 200
    # unknown email does not reveal anything
    r = client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and "debug token" not in r.json()["detail"]


def test_google_login_with_stubbed_verifier(client):
    class StubVerifier:
        def verify(self, id_token: str) -> GoogleIdentity:
            assert id_token == "stub-google-token-123456"
            return GoogleIdentity(sub="g-123", email="google@example.com", email_verified=True, name="Goo Gle", picture=None)

    set_google_verifier(StubVerifier())
    try:
        r = client.post("/api/v1/auth/google", json={"id_token": "stub-google-token-123456"})
        assert r.status_code == 200, r.text
        assert r.json()["is_new_user"] is True
        assert r.json()["user"]["email_verified_at"] is not None
        r = client.post("/api/v1/auth/google", json={"id_token": "stub-google-token-123456"})
        assert r.json()["is_new_user"] is False
    finally:
        set_google_verifier(None)


def test_email_verification_flow(client):
    tokens = register(client, "verify@example.com")
    client.cookies.clear()
    r = client.post("/api/v1/auth/email/verify/request", headers=bearer(tokens))
    token = r.json()["detail"].split("[debug token: ")[1].rstrip("]")
    assert client.post("/api/v1/auth/email/verify/confirm", json={"token": token}).status_code == 200
    me = client.get("/api/v1/users/me", headers=bearer(tokens)).json()
    assert me["user"]["email_verified_at"] is not None
