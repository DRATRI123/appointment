"""Super admin: controlled creation, no silent promotion, recovery, required two-step sign-in, optional IP allow-list."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models import AuditLog, User, UserSession
from app.ops import platform_admin
from app.security import totp
from tests.helpers import bearer, register

STRONG = "Very-Strong-Pass-2026"


@pytest.fixture()
def cli(db, monkeypatch):
    @contextmanager
    def same_session():
        yield db
        db.flush()

    monkeypatch.setattr(platform_admin, "session_scope", same_session)
    return lambda email, **kw: platform_admin.run(email, "Root", password=kw.pop("password", STRONG), **kw)


def test_first_super_admin_is_created_and_a_second_needs_a_flag(cli, db):
    assert "Super admin ready" in cli("root@example.com")
    with pytest.raises(platform_admin.Refused, match="already exists"):
        cli("second@example.com")
    assert "Super admin ready" in cli("second@example.com", add_another=True)
    assert db.scalar(select(AuditLog).where(AuditLog.action == "platform.admin_created")) is not None


def test_ordinary_accounts_are_never_promoted_silently(client, cli, db):
    register(client, "ordinary@example.com")
    with pytest.raises(platform_admin.Refused, match="--promote-existing"):
        cli("ordinary@example.com")
    assert db.scalar(select(User).where(User.email == "ordinary@example.com")).is_platform_admin is False
    cli("ordinary@example.com", promote_existing=True)
    assert db.scalar(select(User).where(User.email == "ordinary@example.com")).is_platform_admin is True


def test_weak_passwords_are_refused(cli):
    with pytest.raises(platform_admin.Refused, match="12 characters"):
        cli("root@example.com", password="Short12345")


def test_recovery_resets_password_and_authenticator_and_signs_out(client, cli, db):
    cli("root@example.com")
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": "root@example.com", "password": STRONG}).status_code == 200
    user = db.scalar(select(User).where(User.email == "root@example.com"))
    user.mfa_enabled_at, user.mfa_secret = user.created_at, "enc:v2:x:y"
    db.flush()
    with pytest.raises(platform_admin.Refused, match="not a super admin"):
        cli("nobody@example.com", recover=True)
    assert "Recovered" in cli("root@example.com", recover=True, password="Brand-New-Pass-2027")
    db.refresh(user)
    assert user.mfa_enabled_at is None and user.mfa_secret is None
    assert all(s.revoked_at is not None for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)))
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": "root@example.com", "password": "Brand-New-Pass-2027"}).status_code == 200
    assert db.scalar(select(AuditLog).where(AuditLog.action == "platform.admin_recovered")) is not None


def test_super_admin_pages_need_two_step_sign_in(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "platform_admin_require_mfa", True)
    h = bearer(register(client, "root2@example.com"))
    db.scalar(select(User).where(User.email == "root2@example.com")).is_platform_admin = True
    db.flush()
    r = client.get("/api/v1/platform/stats", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "mfa_setup_required"
    secret = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]
    assert client.post("/api/v1/auth/mfa/enable", json={"code": totp.code_at(secret)}, headers=h).status_code == 200
    assert client.get("/api/v1/platform/stats", headers=h).status_code == 200


def test_optional_ip_allow_list(client, db, monkeypatch):
    h = bearer(register(client, "root3@example.com"))
    db.scalar(select(User).where(User.email == "root3@example.com")).is_platform_admin = True
    db.flush()
    monkeypatch.setattr(get_settings(), "platform_admin_allowed_ips", ["203.0.113.7/32"])
    r = client.get("/api/v1/platform/stats", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "ip_not_allowed"
    monkeypatch.setattr(get_settings(), "platform_admin_allowed_ips", [])
    assert client.get("/api/v1/platform/stats", headers=h).status_code == 200


def test_production_refuses_super_admins_without_two_step_sign_in():
    from pydantic import ValidationError

    from tests.test_production_config import GOOD_PRODUCTION

    with pytest.raises(ValidationError, match="PLATFORM_ADMIN_REQUIRE_MFA"):
        Settings(_env_file=None, **{**GOOD_PRODUCTION, "platform_admin_require_mfa": False})
