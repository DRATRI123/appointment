"""Embedded admin panel: the clinic's own app shows the admin panel in an iframe; people sign in there separately.

Covers: the clinic setting, the public policy the website uses for frame-ancestors, who may sign in, that a panel
sign-in works only for its clinic (and never as super admin), that turning the panel off or removing the permission
cuts it off at once, separate refresh and sign-out, two-step sign-in, and that no cookie is ever set.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.models import AuditLog, User, UserSession
from app.security import totp
from tests.helpers import PASSWORD, bearer, create_org, otp_login, register

APP = "https://clinic-app.example.com"


@pytest.fixture()
def clinic(client):
    owner_tokens = register(client, "panel-owner@example.com", "Panel Owner")
    owner = bearer(owner_tokens)
    org = create_org(client, owner, "Panel Clinic")
    client.cookies.clear()
    return {"org": org, "owner": {**owner, "X-Organization-Id": org["id"]}}


def _settings(client, clinic, values, expect=200):
    r = client.put(f"/api/v1/organizations/{clinic['org']['id']}/settings/panel", json={"values": values}, headers=clinic["owner"])
    assert r.status_code == expect, r.text
    return r.json()


def _login(client, slug, email="panel-owner@example.com", password=PASSWORD, **extra):
    client.cookies.clear()
    return client.post(f"/api/v1/panel/{slug}/login", json={"email": email, "password": password, **extra})


def _panel(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _member(client, clinic, email, role):
    r = client.post(f"/api/v1/organizations/{clinic['org']['id']}/members", headers=clinic["owner"],
                    json={"identifier": email, "full_name": role, "role_code": role})
    assert r.status_code == 201, r.text
    # Invited by email: the first sign-in is a one-time code; then they set a password.
    h = bearer(otp_login(client, email))
    client.cookies.clear()
    assert client.post("/api/v1/auth/password/change", json={"current_password": None, "new_password": PASSWORD}, headers=h).status_code == 200
    client.cookies.clear()


def test_setting_is_validated_and_the_policy_lists_addresses_only_while_on(client, clinic):
    slug = clinic["org"]["slug"]
    assert client.get(f"/api/v1/panel/{slug}/policy").json() == {"enabled": False, "allowed_origins": [], "organization_name": "Panel Clinic"}
    _settings(client, clinic, {"allowed_origins": ["https://clinic-app.example.com/path"]}, expect=422)
    _settings(client, clinic, {"allowed_origins": ["https://*.example.com"]}, expect=422)
    _settings(client, clinic, {"allowed_origins": [f"https://a{i}.example.com" for i in range(6)]}, expect=422)
    _settings(client, clinic, {"enabled": "yes"}, expect=422)
    _settings(client, clinic, {"something": True}, expect=422)
    saved = _settings(client, clinic, {"allowed_origins": ["HTTPS://Clinic-App.example.com/"]})
    assert saved["values"] == {"enabled": False, "allowed_origins": [APP]}
    assert client.get(f"/api/v1/panel/{slug}/policy").json()["allowed_origins"] == []  # off: nothing may frame it
    _settings(client, clinic, {"enabled": True})
    pol = client.get(f"/api/v1/panel/{slug}/policy")
    assert pol.json()["enabled"] is True and pol.json()["allowed_origins"] == [APP]
    assert client.get("/api/v1/panel/no-such-clinic/policy").status_code == 404


def test_panel_is_a_reserved_clinic_address(client):
    h = bearer(register(client, "slugger@example.com"))
    r = client.post("/api/v1/organizations", json={"name": "Panel", "slug": "panel"}, headers=h)
    assert r.json()["code"] == "slug_reserved", r.text


def test_owner_signs_in_inside_the_panel_without_cookies_and_sees_only_this_clinic(client, db, clinic):
    slug = clinic["org"]["slug"]
    assert _login(client, slug).json()["code"] == "panel_disabled"  # off by default
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    # A second clinic of the same person: the panel sign-in must not reach it.
    other = create_org(client, clinic["owner"], "Other Clinic")
    client.cookies.clear()

    r = _login(client, slug, parent_origin=APP)
    assert r.status_code == 200, r.text
    assert "set-cookie" not in r.headers  # tokens stay in the frame, never in cookies
    tokens = r.json()
    assert tokens["organization_id"] == clinic["org"]["id"]
    h = _panel(tokens)
    me = client.get("/api/v1/users/me", headers=h).json()
    assert [m["organization"]["id"] for m in me["memberships"]] == [clinic["org"]["id"]]
    assert client.get("/api/v1/appointments", headers=h).status_code == 200  # no header needed: the panel's clinic
    r = client.get("/api/v1/appointments", headers={**h, "X-Organization-Id": other["id"]})
    assert r.status_code == 403 and r.json()["code"] == "panel_scope"
    assert client.post("/api/v1/organizations", json={"name": "From Panel"}, headers=h).json()["code"] == "panel_scope"
    session = db.scalar(select(UserSession).where(UserSession.panel_organization_id.is_not(None)))
    assert session.device_label == "Clinic app panel"
    log = db.scalar(select(AuditLog).where(AuditLog.action == "auth.panel_login"))
    assert log.after["parent_origin"] == APP and log.after["in_allowed_list"] is True


def test_only_people_with_the_permission_can_sign_in(client, db, clinic):
    slug = clinic["org"]["slug"]
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    _member(client, clinic, "panel-desk@example.com", "receptionist")
    _member(client, clinic, "panel-admin@example.com", "org_admin")
    r = _login(client, slug, "panel-desk@example.com")
    assert r.status_code == 403 and r.json()["code"] == "panel_not_allowed"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.panel_login_refused")) is not None
    assert _login(client, slug, "panel-admin@example.com").status_code == 200
    assert _login(client, slug, password="wrong-password").json()["code"] == "invalid_credentials"
    # Someone from another clinic cannot sign in to this clinic's panel.
    stranger = bearer(register(client, "panel-stranger@example.com"))
    create_org(client, stranger, "Stranger Clinic")
    assert _login(client, slug, "panel-stranger@example.com").json()["code"] == "panel_not_allowed"


def test_turning_the_panel_off_or_removing_the_permission_cuts_sessions_off(client, db, clinic):
    slug = clinic["org"]["slug"]
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    h = _panel(_login(client, slug).json())
    assert client.get("/api/v1/appointments", headers=h).status_code == 200
    _settings(client, clinic, {"enabled": False})
    r = client.get("/api/v1/appointments", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "panel_disabled"
    _settings(client, clinic, {"enabled": True, "allowed_origins": []})  # on, but no app listed: still closed
    assert client.get("/api/v1/appointments", headers=h).json()["code"] == "panel_disabled"
    _settings(client, clinic, {"allowed_origins": [APP]})
    assert client.get("/api/v1/appointments", headers=h).status_code == 200
    # The owner's ordinary sign-in is untouched by all of this.
    assert client.get("/api/v1/appointments", headers=clinic["owner"]).status_code == 200


def test_refresh_and_sign_out_are_separate_from_the_ordinary_sign_in(client, clinic):
    slug = clinic["org"]["slug"]
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    tokens = _login(client, slug).json()
    # A panel refresh token does not work at the ordinary endpoint, and the other way round.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()["code"] == "refresh_invalid"
    client.cookies.clear()
    ordinary = client.post("/api/v1/auth/login", json={"email": "panel-owner@example.com", "password": PASSWORD}).json()
    client.cookies.clear()
    assert client.post(f"/api/v1/panel/{slug}/refresh", json={"refresh_token": ordinary["refresh_token"]}).json()["code"] == "refresh_invalid"
    r = client.post(f"/api/v1/panel/{slug}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and "set-cookie" not in r.headers
    fresh = r.json()
    assert client.get("/api/v1/appointments", headers=_panel(fresh)).status_code == 200
    assert client.post("/api/v1/panel/logout", json={"refresh_token": ordinary["refresh_token"]}).status_code == 401  # only panel sessions
    assert client.post("/api/v1/panel/logout", json={"refresh_token": fresh["refresh_token"]}).status_code == 204
    assert client.get("/api/v1/appointments", headers=_panel(fresh)).status_code == 401
    assert client.get("/api/v1/appointments", headers={**bearer(ordinary), "X-Organization-Id": clinic["org"]["id"]}).status_code == 200


def test_two_step_sign_in_finishes_only_inside_the_panel(client, clinic):
    slug = clinic["org"]["slug"]
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    setup = client.post("/api/v1/auth/mfa/setup", headers=clinic["owner"]).json()
    assert client.post("/api/v1/auth/mfa/enable", json={"code": totp.code_at(setup["secret"])}, headers=clinic["owner"]).status_code == 200
    r = _login(client, slug)
    assert r.status_code == 401 and r.json()["code"] == "mfa_required"
    mfa_token = r.json()["mfa_token"]
    code = totp.code_at(setup["secret"], time.time() + totp.PERIOD)
    # The ordinary second step refuses a token started in the panel (it would set cookies).
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code}).json()["code"] == "mfa_token_invalid"
    r = client.post(f"/api/v1/panel/{slug}/mfa", json={"mfa_token": mfa_token, "code": code})
    assert r.status_code == 200, r.text
    assert "set-cookie" not in r.headers
    assert client.get("/api/v1/appointments", headers=_panel(r.json())).status_code == 200


def test_a_super_admin_gets_no_super_admin_powers_through_the_panel(client, db, clinic):
    slug = clinic["org"]["slug"]
    _settings(client, clinic, {"enabled": True, "allowed_origins": [APP]})
    db.scalar(select(User).where(User.email == "panel-owner@example.com")).is_platform_admin = True
    db.commit()
    h = _panel(_login(client, slug).json())
    assert client.get("/api/v1/users/me", headers=h).json()["is_platform_admin"] is False
    assert client.get("/api/v1/platform/stats", headers=h).status_code == 403
