"""Every staff role against real endpoints. The expected answer for each comes from ROLE_PERMISSIONS (the same table
docs/permissions-matrix.md is generated from), so the code, the document and the behaviour cannot drift apart."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.enums import SystemRole
from app.security.permissions import ROLE_PERMISSIONS
from tests.helpers import bearer, create_org, otp_login, register

# (method, path template, the permission(s) the endpoint requires, JSON body)
CHECKS = [
    ("GET", "/branches", "branches:read", None),
    ("POST", "/branches", "branches:write", {"name": "Matrix Branch", "code": "MTX"}),
    ("POST", "/services", "services:write", {"name": "Matrix Service", "duration_minutes": 30, "price_paise": 10000, "payment_mode": "pay_at_clinic"}),
    ("GET", "/customers", "customers:read", None),
    ("POST", "/customers", "customers:write", {"full_name": "Matrix Patient", "mobile": "9876500000"}),
    ("GET", "/payments", "payments:read", None),
    ("GET", "/admin/payments/queue", "payments:verify", None),
    ("GET", "/organizations/{org}/audit-logs", "audit_logs:read", None),
    ("GET", "/organizations/{org}/members", "staff:read", None),
    ("PUT", "/organizations/{org}/settings/booking", "organization:write", {"values": {"hold_minutes": 10}}),
    ("GET", "/developers/api-keys", "api_keys:manage", None),
    ("GET", "/upi-accounts", "upi_accounts:read", None),
    ("GET", "/reports/payments", ("reports:read", "payments:read"), None),  # a money report needs both
]
STAFF_ROLES = [r for r in SystemRole if r not in (SystemRole.PLATFORM_SUPER_ADMIN, SystemRole.CUSTOMER, SystemRole.ORG_OWNER)]


@pytest.fixture()
def clinic(client):
    owner = bearer(register(client, "matrix-owner@example.com", "Matrix Owner"))
    org = create_org(client, owner, "Matrix Clinic")
    return {"org": org, "owner": {**owner, "X-Organization-Id": org["id"]}}


@pytest.mark.parametrize("role", STAFF_ROLES, ids=lambda r: r.value)
def test_each_role_gets_exactly_its_permissions(client, clinic, role):
    org = clinic["org"]
    mobile = f"97{abs(hash(role.value)) % 10**8:08d}"
    r = client.post(f"/api/v1/organizations/{org['id']}/members", headers=clinic["owner"],
                    json={"identifier": mobile, "full_name": f"{role.value} user", "role_code": role.value})
    assert r.status_code == 201, r.text
    h = {**bearer(otp_login(client, mobile)), "X-Organization-Id": org["id"]}
    client.cookies.clear()
    granted = set(ROLE_PERMISSIONS[role])
    wrong = []
    for method, path, permission, body in CHECKS:
        res = client.request(method, f"/api/v1{path.format(org=org['id'])}", headers=h, json=body)
        needed = {permission} if isinstance(permission, str) else set(permission)
        allowed = needed <= granted
        if allowed and res.status_code in (401, 403):
            wrong.append(f"{method} {path}: should be allowed ({permission}) but got {res.status_code} {res.text[:120]}")
        if not allowed and res.status_code != 403:
            wrong.append(f"{method} {path}: should be refused (no {permission}) but got {res.status_code}")
    assert wrong == []


def test_staff_cannot_reach_the_super_admin_pages(client, clinic):
    assert client.get("/api/v1/platform/stats", headers=clinic["owner"]).status_code == 403


def test_a_role_cannot_grant_itself_more(client, clinic):
    """Privilege escalation: a member without staff:write cannot invite or promote anyone."""
    org = clinic["org"]
    client.post(f"/api/v1/organizations/{org['id']}/members", headers=clinic["owner"],
                json={"identifier": "9612340000", "full_name": "Desk", "role_code": "receptionist"})
    h = {**bearer(otp_login(client, "9612340000")), "X-Organization-Id": org["id"]}
    client.cookies.clear()
    r = client.post(f"/api/v1/organizations/{org['id']}/members", headers=h,
                    json={"identifier": "9612340001", "full_name": "Me Again", "role_code": "org_admin"})
    assert r.status_code == 403


def test_the_permissions_document_is_up_to_date():
    from app.ops.permissions_matrix import render

    doc = Path(__file__).resolve().parents[2] / "docs" / "permissions-matrix.md"
    assert doc.exists(), "run: python -m app.ops.permissions_matrix"
    assert doc.read_text(encoding="utf-8") == render(), "docs/permissions-matrix.md is out of date: run python -m app.ops.permissions_matrix"
