"""Helpers shared by Phase 2+ tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

PASSWORD = "Str0ngPass123"


def register(client: TestClient, email: str, name: str = "Test User") -> dict:
    r = client.post("/api/v1/auth/register", json={"full_name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


def bearer(token_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def otp_login(client: TestClient, identifier: str, full_name: str | None = None) -> dict:
    r = client.post("/api/v1/auth/otp/request", json={"identifier": identifier})
    assert r.status_code == 200, r.text
    code = r.json()["debug_code"]
    r = client.post("/api/v1/auth/otp/verify", json={"identifier": identifier, "code": code, "full_name": full_name})
    assert r.status_code == 200, r.text
    return r.json()


def create_org(client: TestClient, headers: dict, name: str, **extra) -> dict:
    r = client.post("/api/v1/organizations", json={"name": name, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def clinic_google_app(db, org_public_id: str, client_id: str = "clinic-app-1.apps.googleusercontent.com", secret: str = "clinic-google-secret"):
    """The clinic's own Google Cloud app, saved and tested (all of a clinic's Google connections use it)."""
    import json

    from sqlalchemy import select

    from app.models import Integration, Organization
    from app.security.crypto import encrypt_text

    org = db.scalar(select(Organization).where(Organization.public_id == org_public_id))
    row = Integration(organization_id=org.id, provider="google_app", name="Google Cloud app", status="connected", is_enabled=True,
                      config={"client_id": client_id, "_hints": {"client_secret": "…cret"}, "_last_test": {"ok": True, "message": "ok", "at": "2026-11-16T00:00:00"}},
                      credentials_encrypted=encrypt_text(json.dumps({"client_secret": secret})))
    db.add(row)
    db.flush()
    return row
