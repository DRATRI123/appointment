from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import Tenant, get_db
from app.main import create_app
from app.models import User
from tests.helpers import bearer, create_org, otp_login, register


def _setup_two_orgs(client):
    a = register(client, "owner-a@example.com", "Owner A")
    client.cookies.clear()
    b = register(client, "owner-b@example.com", "Owner B")
    client.cookies.clear()
    org_a = create_org(client, bearer(a), "Acme Clinic", slug="acme-clinic")
    org_b = create_org(client, bearer(b), "Beta Wellness")
    return a, b, org_a, org_b


def test_owner_membership_and_me_permissions(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    me = client.get("/api/v1/users/me", headers=bearer(a)).json()
    assert len(me["memberships"]) == 1
    m = me["memberships"][0]
    assert m["organization"]["slug"] == "acme-clinic"
    assert m["role_code"] == "org_owner"
    assert "payments:verify" in m["permissions"]
    assert not any(p.startswith("platform:") for p in m["permissions"])
    assert org_a["code"].startswith("ACME")


def test_tenant_isolation_between_organizations(client):
    a, b, org_a, org_b = _setup_two_orgs(client)
    # A cannot read, update or list members of B.
    assert client.get(f"/api/v1/organizations/{org_b['id']}", headers=bearer(a)).status_code == 403
    assert client.patch(f"/api/v1/organizations/{org_b['id']}", json={"name": "Hacked"}, headers=bearer(a)).status_code == 403
    assert client.get(f"/api/v1/organizations/{org_b['id']}/members", headers=bearer(a)).status_code == 403
    assert client.get(f"/api/v1/organizations/{org_b['id']}/audit-logs", headers=bearer(a)).status_code == 403
    # B's name is unchanged.
    assert client.get(f"/api/v1/organizations/{org_b['id']}", headers=bearer(b)).json()["name"] == "Beta Wellness"
    # Own org works.
    assert client.get(f"/api/v1/organizations/{org_a['id']}", headers=bearer(a)).status_code == 200


def test_receptionist_permissions_are_enforced(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    r = client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "9111111111", "full_name": "Front Desk", "role_code": "receptionist"},
        headers=bearer(a),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "invited"

    # Receptionist signs in via OTP; invitation activates.
    rec = otp_login(client, "9111111111")
    client.cookies.clear()
    me = client.get("/api/v1/users/me", headers=bearer(rec)).json()
    assert me["memberships"][0]["status"] == "active"
    assert me["memberships"][0]["role_code"] == "receptionist"

    # Read allowed, staff management denied, settings write denied.
    assert client.get(f"/api/v1/organizations/{org_a['id']}", headers=bearer(rec)).status_code == 200
    r = client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "9222222222", "full_name": "X", "role_code": "staff"},
        headers=bearer(rec),
    )
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert client.put(f"/api/v1/organizations/{org_a['id']}/settings/payment", json={"values": {"allow_cash": False}}, headers=bearer(rec)).status_code == 403
    assert client.get(f"/api/v1/organizations/{org_a['id']}/audit-logs", headers=bearer(rec)).status_code == 403


def test_only_owner_can_assign_owner_and_last_owner_protected(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    r = client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "admin-a@example.com", "full_name": "Admin A", "role_code": "org_admin"},
        headers=bearer(a),
    )
    admin_membership = r.json()
    admin = otp_login(client, "admin-a@example.com")
    client.cookies.clear()
    # Admin cannot promote someone to owner.
    r = client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "9333333333", "full_name": "New Owner", "role_code": "org_owner"},
        headers=bearer(admin),
    )
    assert r.status_code == 403 and r.json()["code"] == "owner_only"
    # Owner cannot demote themself as the last owner.
    members = client.get(f"/api/v1/organizations/{org_a['id']}/members", headers=bearer(a)).json()
    owner_membership = next(m for m in members if m["role_code"] == "org_owner")
    r = client.patch(
        f"/api/v1/organizations/{org_a['id']}/members/{owner_membership['id']}",
        json={"role_code": "staff"}, headers=bearer(a),
    )
    assert r.status_code == 409 and r.json()["code"] == "last_owner"
    # Owner promotes admin to owner, then can step down.
    r = client.patch(
        f"/api/v1/organizations/{org_a['id']}/members/{admin_membership['id']}",
        json={"role_code": "org_owner"}, headers=bearer(a),
    )
    assert r.status_code == 200 and r.json()["role_code"] == "org_owner"
    r = client.patch(
        f"/api/v1/organizations/{org_a['id']}/members/{owner_membership['id']}",
        json={"role_code": "org_admin"}, headers=bearer(a),
    )
    assert r.status_code == 200


def test_custom_roles_and_privilege_escalation_guard(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    r = client.get(f"/api/v1/organizations/{org_a['id']}/roles", headers=bearer(a))
    codes = {role["code"] for role in r.json()}
    assert "receptionist" in codes and "platform_super_admin" not in codes

    r = client.post(
        f"/api/v1/organizations/{org_a['id']}/roles",
        json={"code": "billing_clerk", "name": "Billing clerk", "permissions": ["payments:read", "payments:verify"]},
        headers=bearer(a),
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    assert r.json()["is_custom"] is True

    # Platform permissions can never be granted to organization roles.
    r = client.patch(f"/api/v1/organizations/{org_a['id']}/roles/{role_id}", json={"permissions": ["platform:manage"]}, headers=bearer(a))
    assert r.status_code == 403

    # A branch manager (holds roles:write? no) -> an org_admin without 'organization:billing' cannot grant it.
    client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "admin2@example.com", "full_name": "Admin Two", "role_code": "org_admin"},
        headers=bearer(a),
    )
    admin = otp_login(client, "admin2@example.com")
    client.cookies.clear()
    r = client.patch(
        f"/api/v1/organizations/{org_a['id']}/roles/{role_id}",
        json={"permissions": ["payments:read", "organization:billing"]}, headers=bearer(admin),
    )
    assert r.status_code == 403 and r.json()["code"] == "privilege_escalation"

    # Assign the custom role, then deletion is blocked while in use.
    client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"identifier": "9444444444", "full_name": "Clerk", "role_code": "billing_clerk"},
        headers=bearer(a),
    )
    r = client.delete(f"/api/v1/organizations/{org_a['id']}/roles/{role_id}", headers=bearer(a))
    assert r.status_code == 409 and r.json()["code"] == "role_in_use"


def test_settings_defaults_update_and_audit_log(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    r = client.get(f"/api/v1/organizations/{org_a['id']}/settings/booking", headers=bearer(a))
    assert r.status_code == 200
    assert r.json()["values"]["hold_minutes"] == 10
    r = client.put(f"/api/v1/organizations/{org_a['id']}/settings/booking", json={"values": {"hold_minutes": 15, "allow_guest_booking": False}}, headers=bearer(a))
    assert r.status_code == 200
    assert r.json()["values"]["hold_minutes"] == 15
    assert r.json()["values"]["allow_guest_booking"] is False
    assert client.get(f"/api/v1/organizations/{org_a['id']}/settings/unknown", headers=bearer(a)).status_code == 404

    logs = client.get(f"/api/v1/organizations/{org_a['id']}/audit-logs", headers=bearer(a)).json()
    actions = [row["action"] for row in logs["data"]]
    assert "organization.settings_updated" in actions and "organization.created" in actions
    assert logs["meta"]["total"] >= 2


def test_multi_org_user_must_pick_organization_via_header(client):
    a, _, org_a, _ = _setup_two_orgs(client)
    org_a2 = create_org(client, bearer(a), "Acme Second")
    # Routes without an organization path parameter resolve the tenant from X-Organization-Id.
    app = create_app()

    @app.get("/whoami")
    def whoami(ctx: Tenant):
        return {"org": ctx.organization.public_id, "role": ctx.role_code}

    app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
    with TestClient(app) as c:
        r = c.get("/whoami", headers=bearer(a))
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "organization_required", r.text
        r = c.get("/whoami", headers={**bearer(a), "X-Organization-Id": org_a2["id"]})
        assert r.status_code == 200, r.text
        assert r.json() == {"org": org_a2["id"], "role": "org_owner"}
        r = c.get("/whoami", headers={**bearer(a), "X-Organization-Id": "00000000-0000-0000-0000-000000000000"})
        assert r.status_code == 404


def test_platform_admin_access_is_audited_and_can_suspend(client, db):
    a, b, org_a, org_b = _setup_two_orgs(client)
    register(client, "root@example.com", "Root")
    client.cookies.clear()
    root = db.scalar(select(User).where(User.email == "root@example.com"))
    root.is_platform_admin = True
    db.flush()
    root_tokens = client.post("/api/v1/auth/login", json={"email": "root@example.com", "password": "Str0ngPass123"}).json()
    client.cookies.clear()

    # Non-admin blocked from platform routes.
    assert client.get("/api/v1/platform/organizations", headers=bearer(a)).status_code == 403
    r = client.get("/api/v1/platform/organizations", headers=bearer(root_tokens))
    assert r.status_code == 200 and r.json()["meta"]["total"] == 2

    # Platform admin can read B without membership; the access is audited.
    assert client.get(f"/api/v1/organizations/{org_b['id']}", headers=bearer(root_tokens)).status_code == 200
    logs = client.get(f"/api/v1/organizations/{org_b['id']}/audit-logs", headers=bearer(b)).json()
    assert any(row["action"] == "platform.impersonate" for row in logs["data"])

    # Suspend B: owner B is locked out of tenant routes.
    r = client.post(f"/api/v1/platform/organizations/{org_b['id']}/status", json={"status": "suspended", "reason": "unpaid"}, headers=bearer(root_tokens))
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    r = client.get(f"/api/v1/organizations/{org_b['id']}", headers=bearer(b))
    assert r.status_code == 403 and r.json()["code"] == "organization_inactive"
    # Public slug lookup hides suspended organizations.
    assert client.get("/api/v1/organizations/by-slug/acme-clinic").status_code == 200
    assert client.get(f"/api/v1/organizations/by-slug/{org_b['slug']}").status_code == 404

    # Suspending a user revokes their sessions.
    me_b = client.get("/api/v1/users/me", headers=bearer(b)).json()
    r = client.post(f"/api/v1/platform/users/{me_b['user']['id']}/status", json={"status": "suspended"}, headers=bearer(root_tokens))
    assert r.status_code == 200
    assert client.get("/api/v1/users/me", headers=bearer(b)).status_code in (401, 403)
    stats = client.get("/api/v1/platform/stats", headers=bearer(root_tokens)).json()
    assert stats["organizations_total"] == 2 and stats["organizations_active"] == 1
