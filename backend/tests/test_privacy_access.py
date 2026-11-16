"""Privacy module: masking, reveal, re-authentication, screen lock, idle sign-out, exports, signed document links,
bulk-access detection, tamper-evident audit rows, no-store responses, settings validation, virus scanning and the
controlled PDF export."""
from __future__ import annotations

import io
import socket
import threading
import zlib
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.time import utcnow
from app.models import AuditLog, User, UserSession
from tests.booking_helpers import Clinic, ist
from tests.helpers import PASSWORD, bearer, otp_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _stale(db, email: str) -> None:
    """Pretend the last sign-in / confirmation was an hour ago."""
    uid = db.scalar(select(User.id).where(User.email == email))
    db.execute(update(UserSession).where(UserSession.user_id == uid).values(reauthenticated_at=utcnow() - timedelta(hours=1)))
    db.flush()


def _audit(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="priv-owner@example.com", name="Privacy Clinic", payment_mode="pay_at_clinic")


@pytest.fixture()
def storage(tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.EncryptingStorage(storage_module.LocalStorage(tmp_path))
    yield tmp_path
    storage_module._storage = None


# ------------------------------------------------------------------------------------------------------- masking
def test_staff_see_masked_contacts_everywhere_patient_sees_own(client, db, clinic):
    hold = clinic.public_hold(ist(clinic.monday, 9))
    own = clinic.public_book(hold["id"], customer={"full_name": "Asha", "mobile": "9876543210", "email": "atreya.patel@example.com"})
    assert own["customer"]["mobile"] == "+919876543210"  # the patient's own booking: not masked
    cust_id = own["customer"]["id"]
    staff_views = [
        clinic.get(f"/customers/{cust_id}"),
        clinic.get("/customers")["data"][0],
        clinic.get(f"/appointments/{own['id']}")["customer"],
    ]
    for v in staff_views:
        assert v["mobile"] == "+9198765XXXXX" and v["email"] == "atr***@example.com"
    assert "9876543210" not in str(clinic.get("/appointments", {"page_size": 50}))

    # Saving a form that loaded the masked values keeps the real ones; the audit log shows only masked values.
    r = clinic.client.patch(f"/api/v1/customers/{cust_id}", json={"mobile": "+9198765XXXXX", "email": "atr***@example.com", "blood_group": "O+"},
                            headers=clinic.h)
    assert r.status_code == 200, r.text
    full = clinic.post(f"/customers/{cust_id}/reveal", {}, expect=200)
    assert full["mobile"] == "+919876543210" and full["email"] == "atreya.patel@example.com"
    r = clinic.client.patch(f"/api/v1/customers/{cust_id}", json={"mobile": "9876500000"}, headers=clinic.h)
    assert r.status_code == 200
    updated = [a for a in _audit(db, "customer.updated") if a.after and "mobile" in a.after][-1]
    assert "9876543210" not in str(updated.before) and "9876500000" not in str(updated.after)

    # A clinic can switch masking off.
    clinic.put(f"/organizations/{clinic.org['id']}/settings/privacy", {"values": {"mask_contact_details": False}})
    assert clinic.get(f"/customers/{cust_id}")["mobile"] == "+919876500000"


def test_reveal_needs_permission_recent_confirmation_and_is_audited(client, db, clinic):
    cust = clinic.post("/customers", {"full_name": "Reveal Me", "mobile": "9811122233"})
    r = clinic.client.post(f"/api/v1/customers/{cust['id']}/reveal", json={"purpose": "call about report"}, headers=clinic.h)
    assert r.status_code == 200 and r.json()["mobile"] == "+919811122233"
    row = _audit(db, "customer.contact_revealed")[-1]
    assert row.purpose == "call about report" and "9811122233" not in str(row.after)

    # An hour later the owner must confirm it is them again (password), then it works.
    _stale(db, "priv-owner@example.com")
    r = clinic.client.post(f"/api/v1/customers/{cust['id']}/reveal", json={}, headers=clinic.h)
    assert r.status_code == 403 and r.json()["code"] == "reauth_required"
    bad = clinic.client.post("/api/v1/auth/reauth", json={"password": "wrong-password-9"}, headers=clinic.h)
    assert bad.status_code == 401 and bad.json()["code"] == "reauth_failed"
    assert clinic.client.post("/api/v1/auth/reauth", json={"password": PASSWORD}, headers=clinic.h).status_code == 200
    assert clinic.client.post(f"/api/v1/customers/{cust['id']}/reveal", json={}, headers=clinic.h).status_code == 200

    # Staff without customers:reveal cannot (the "staff" role reads appointments only).
    clinic.post(f"/organizations/{clinic.org['id']}/members", {"identifier": "9622200009", "full_name": "Helper", "role_code": "staff"})
    hs = {**bearer(otp_login(client, "9622200009")), "X-Organization-Id": clinic.org["id"]}
    client.cookies.clear()
    assert client.post(f"/api/v1/customers/{cust['id']}/reveal", json={}, headers=hs).status_code == 403


def test_code_signin_accounts_confirm_with_a_fresh_code(client, db, clinic):
    clinic.post(f"/organizations/{clinic.org['id']}/members", {"identifier": "9622200010", "full_name": "Desk", "role_code": "receptionist"})
    tokens = otp_login(client, "9622200010")
    client.cookies.clear()
    h = {**bearer(tokens), "X-Organization-Id": clinic.org["id"]}
    uid = db.scalar(select(User.id).where(User.mobile == "+919622200010"))
    db.execute(update(UserSession).where(UserSession.user_id == uid).values(reauthenticated_at=utcnow() - timedelta(hours=1)))
    cust = clinic.post("/customers", {"full_name": "Code Patient", "mobile": "9811122244"})
    assert client.post(f"/api/v1/customers/{cust['id']}/reveal", json={}, headers=h).json()["code"] == "reauth_required"
    sent = client.post("/api/v1/auth/reauth/send-code", headers=h)
    assert sent.status_code == 200, sent.text
    assert client.post("/api/v1/auth/reauth", json={"otp_code": "000000"}, headers=h).status_code == 401
    assert client.post("/api/v1/auth/reauth", json={"otp_code": sent.json()["debug_code"]}, headers=h).status_code == 200
    assert client.post(f"/api/v1/customers/{cust['id']}/reveal", json={}, headers=h).status_code == 200


# --------------------------------------------------------------------------------------------- lock and sessions
def test_locked_screen_blocks_the_api_until_confirmed(client, clinic):
    assert clinic.client.post("/api/v1/auth/lock", headers=clinic.h).status_code == 200
    r = clinic.client.get("/api/v1/customers", headers=clinic.h)
    assert r.status_code == 403 and r.json()["code"] == "session_locked"
    assert clinic.client.get("/api/v1/users/me", headers=clinic.h).status_code == 200  # the lock screen can show who it is
    assert clinic.client.post("/api/v1/auth/reauth", json={"password": PASSWORD}, headers=clinic.h).status_code == 200
    assert clinic.client.get("/api/v1/customers", headers=clinic.h).status_code == 200


def test_idle_device_is_signed_out_and_refresh_keeps_lock_and_confirmation_time(client, db):
    from app.services.auth_service import AuthService

    r = client.post("/api/v1/auth/register", json={"full_name": "Idle", "email": "idle@example.com", "password": PASSWORD})
    refresh = r.json()["refresh_token"]
    uid = db.scalar(select(User.id).where(User.email == "idle@example.com"))
    old = utcnow() - timedelta(hours=1)
    db.execute(update(UserSession).where(UserSession.user_id == uid).values(reauthenticated_at=old, locked_at=utcnow()))
    result = AuthService(db).refresh(refresh)
    assert result.session.reauthenticated_at is not None and abs((result.session.reauthenticated_at - old).total_seconds()) < 1
    assert result.session.locked_at is not None  # refreshing a token never unlocks the screen
    result.session.last_seen_at = utcnow() - timedelta(days=2)
    db.flush()
    from app.core.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError, match="without use"):
        AuthService(db).refresh(result.refresh_token)


def test_admins_sign_out_staff_and_super_admins_any_account(client, db, clinic):
    clinic.post(f"/organizations/{clinic.org['id']}/members", {"identifier": "9622200011", "full_name": "Leaver", "role_code": "receptionist"})
    staff_tokens = otp_login(client, "9622200011")
    client.cookies.clear()
    hs = {**bearer(staff_tokens), "X-Organization-Id": clinic.org["id"]}
    members = clinic.get(f"/organizations/{clinic.org['id']}/members")
    member = next(m for m in (members["data"] if isinstance(members, dict) else members) if m.get("full_name") == "Leaver" or m.get("user", {}).get("full_name") == "Leaver")
    sessions = clinic.get(f"/organizations/{clinic.org['id']}/members/{member['id']}/sessions")
    assert len(sessions) == 1 and "ip" not in str(sessions[0]).lower()
    r = clinic.client.post(f"/api/v1/organizations/{clinic.org['id']}/members/{member['id']}/sessions/revoke", headers=clinic.h)
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/customers", headers=hs).status_code == 401  # signed out at once
    assert _audit(db, "staff.sessions_revoked")


# --------------------------------------------------------------------------------------------------- exports
def test_exports_need_confirmation_and_respect_daily_and_row_limits(client, db, clinic):
    clinic.post("/customers", {"full_name": "Exported", "mobile": "9811122255"})
    assert clinic.client.get("/api/v1/customers/export.csv", headers=clinic.h).status_code == 200
    _stale(db, "priv-owner@example.com")
    assert clinic.client.get("/api/v1/customers/export.csv", headers=clinic.h).json()["code"] == "reauth_required"
    clinic.client.post("/api/v1/auth/reauth", json={"password": PASSWORD}, headers=clinic.h)
    clinic.put(f"/organizations/{clinic.org['id']}/settings/privacy", {"values": {"max_exports_per_day": 2}})
    assert clinic.client.get("/api/v1/customers/export.csv", headers=clinic.h).status_code == 200
    r = clinic.client.get("/api/v1/customers/export.csv", headers=clinic.h)
    assert r.status_code == 429 and r.json()["code"] == "export_limit"
    clinic.put(f"/organizations/{clinic.org['id']}/settings/privacy", {"values": {"max_exports_per_day": 50, "max_export_rows": 100}})
    for i in range(101):
        db.add(__import__("app.models", fromlist=["Customer"]).Customer(organization_id=db.scalar(
            select(__import__("app.models", fromlist=["Organization"]).Organization.id).where(
                __import__("app.models", fromlist=["Organization"]).Organization.public_id == clinic.org["id"])), full_name=f"Bulk {i}"))
    db.flush()
    r = clinic.client.get("/api/v1/customers/export.csv", headers=clinic.h)
    assert r.status_code == 422 and r.json()["code"] == "export_too_large"


def test_controlled_pdf_summary_is_watermarked_and_audited(client, db, clinic):
    cust = clinic.post("/customers", {"full_name": "Pdf Patient", "mobile": "9811122266"})
    clinic.post(f"/customers/{cust['id']}/notes", {"body": "Mild asthma", "note_type": "allergy"})
    r = clinic.client.get(f"/api/v1/customers/{cust['id']}/summary.pdf", headers=clinic.h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-1.4")
    assert "no-store" in r.headers["cache-control"]
    streams = b"".join(zlib.decompress(part.split(b"stream\n", 1)[1]) for part in r.content.split(b"endstream")[:-1] if b"FlateDecode" in part)
    assert b"CONFIDENTIAL" in streams and b"Exported by U-" in streams and b"Mild asthma" in streams
    assert b"priv-owner" not in streams  # the watermark identifies the account without personal data
    assert _audit(db, "customer.summary_exported")


# ------------------------------------------------------------------------------------------- signed document links
def test_signed_document_links_are_short_lived_personal_and_rechecked(client, db, clinic, storage, monkeypatch):
    cust = clinic.post("/customers", {"full_name": "Doc Link", "mobile": "9811122277"})
    up = clinic.client.post(f"/api/v1/customers/{cust['id']}/documents", files={"file": ("r.png", io.BytesIO(PNG), "image/png")},
                            data={"title": 'Scan"; evil=1\r\nX: y', "document_type": "report"}, headers=clinic.h)
    assert up.status_code == 201, up.text
    link = clinic.post(f"/customers/{cust['id']}/documents/{up.json()['id']}/link", {}, expect=200)
    assert link["url"].startswith("/api/v1/files/") and link["expires_in"] == 60
    client.cookies.clear()
    r = client.get(link["url"])  # no Authorization header: the link itself is the permission
    assert r.status_code == 200 and r.content == PNG and r.headers["cache-control"] == "private, no-store"
    assert "\r" not in r.headers["content-disposition"] and "evil" not in r.headers["content-disposition"].split("filename=")[0]
    tampered = link["url"][:-1] + ("0" if link["url"][-1] != "0" else "1")
    assert client.get(tampered).status_code == 404
    import time as _time

    real = _time.time
    monkeypatch.setattr(_time, "time", lambda: real() + 120)
    assert client.get(link["url"]).json()["code"] == "link_expired"
    monkeypatch.setattr(_time, "time", real)
    clinic.client.post("/api/v1/auth/sessions/revoke-all", headers=clinic.h)
    assert client.get(link["url"]).status_code == 401  # signed out: the link stops working too


# ---------------------------------------------------------------------------------------------- bulk access
def test_opening_many_patients_alerts_then_blocks(client, db, clinic):
    clinic.put(f"/organizations/{clinic.org['id']}/settings/privacy", {"values": {"bulk_access_alert_per_hour": 10, "bulk_access_block_per_hour": 20}})
    ids = [clinic.post("/customers", {"full_name": f"Patient {i}", "mobile": f"98111{i:05d}"})["id"] for i in range(21)]
    for cid in ids[:20]:
        assert clinic.client.get(f"/api/v1/customers/{cid}", headers=clinic.h).status_code == 200
    assert clinic.client.get(f"/api/v1/customers/{ids[0]}", headers=clinic.h).status_code == 200  # the same patient again is fine
    r = clinic.client.get(f"/api/v1/customers/{ids[20]}", headers=clinic.h)
    assert r.status_code == 429 and r.json()["code"] == "bulk_access_blocked"
    assert len(_audit(db, "security.bulk_access_detected")) == 1


# -------------------------------------------------------------------------------------------- audit integrity
def test_audit_rows_are_signed_and_tampering_is_detected(client, db, clinic, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy import text as sql_text

    from app.ops import verify_audit

    @contextmanager
    def same():
        yield db

    monkeypatch.setattr(verify_audit, "session_scope", same)
    clinic.post("/customers", {"full_name": "Audited", "mobile": "9811122288"})
    result = verify_audit.verify()
    assert result["checked"] > 0 and result["altered"] == 0
    row = _audit(db, "customer.created")[-1]
    if db.get_bind().dialect.name == "postgresql":
        # The trigger refuses this edit; an attacker with full database rights could switch triggers off first.
        # The signature must catch the edit even then.
        db.execute(sql_text("SET LOCAL session_replication_role = replica"))
    db.execute(update(AuditLog).where(AuditLog.id == row.id).values(action="customer.deleted"))  # an attacker with DB access
    db.expire_all()
    result = verify_audit.verify()
    assert result["altered"] == 1 and row.public_id in result["altered_rows"][0]


# ------------------------------------------------------------------------------------------- browser hygiene
def test_private_api_answers_are_not_cached(client, clinic):
    r = clinic.client.get("/api/v1/customers", headers=clinic.h)
    assert r.headers["cache-control"] == "no-store" and r.headers["pragma"] == "no-cache"
    pub = client.get(f"/api/v1/public/organizations/{clinic.org['slug']}/website")
    assert pub.headers["cache-control"] != "no-store" or pub.status_code != 200  # public pages keep their own short cache


FORBIDDEN_FIELDS = {"password_hash", "code_hash", "refresh_token_hash", "token_hash", "mfa_secret", "mfa_recovery_hashes", "secrets_encrypted",
                    "credentials_encrypted", "secret_encrypted", "body_encrypted", "key_hash", "otp", "otp_code", "encryption_key",
                    "data_encryption_key", "secret_key", "database_url", "storage_path"}


def test_no_api_response_can_contain_secrets_or_hashes(client):
    """Every schema any endpoint can RESPOND with (followed through nested references): none may carry a hash, key,
    secret or storage path. Request bodies (e.g. the code someone types to confirm it is them) are not responses."""
    spec = client.get("/api/v1/openapi.json").json()
    schemas = spec["components"]["schemas"]
    seen: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref:
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    walk(schemas[name])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for methods in spec["paths"].values():
        for op in methods.values():
            for resp in (op.get("responses") or {}).values():
                walk(resp.get("content", {}))
    assert len(seen) > 50  # sanity: the walk found the response models
    bad = sorted(f"{name}.{prop}" for name in seen for prop in schemas[name].get("properties", {}) if prop in FORBIDDEN_FIELDS)
    assert bad == []


def test_privacy_settings_are_validated_and_need_confirmation(client, db, clinic):
    url = f"/api/v1/organizations/{clinic.org['id']}/settings/privacy"
    for bad in ({"watermark_opacity": 0.9}, {"print_policy": "sometimes"}, {"lock_after_minutes_by_role": {"hacker": 1}},
                {"bulk_access_alert_per_hour": 100, "bulk_access_block_per_hour": 50}, {"mask_contact_details": "no"}):
        assert clinic.client.put(url, json={"values": bad}, headers=clinic.h).status_code == 422, bad
    _stale(db, "priv-owner@example.com")
    assert clinic.client.put(url, json={"values": {"watermark_opacity": 0.1}}, headers=clinic.h).json()["code"] == "reauth_required"
    me = clinic.client.get("/api/v1/users/me/privacy", headers=clinic.h).json()
    assert me["lock_after_minutes"] == 15 and me["user_ref"].startswith("U-") and "@" not in str(me)


# ------------------------------------------------------------------------------------------------- virus scan
def _fake_clamd(reply: bytes) -> int:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        with conn:
            data = b""
            while not data.endswith(b"\0\0\0\0"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            conn.sendall(reply)
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def test_optional_virus_scan_blocks_infected_files_and_fails_closed(monkeypatch):
    from app.core import virus_scan
    from app.core.config import get_settings
    from app.core.exceptions import ServiceUnavailable, ValidationFailed
    from app.core.storage import validate_upload

    s = get_settings()
    monkeypatch.setattr(s, "upload_scanner", "clamav")
    monkeypatch.setattr(s, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(s, "clamav_port", _fake_clamd(b"stream: OK\0"))
    assert validate_upload(PNG, allowed={"image/png"}, max_mb=1) == "image/png"
    monkeypatch.setattr(s, "clamav_port", _fake_clamd(b"stream: Eicar-Test-Signature FOUND\0"))
    with pytest.raises(ValidationFailed, match="malware"):
        validate_upload(PNG, allowed={"image/png"}, max_mb=1)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    monkeypatch.setattr(s, "clamav_port", port)
    with pytest.raises(ServiceUnavailable):
        validate_upload(PNG, allowed={"image/png"}, max_mb=1)
    assert virus_scan.scan_upload  # default (none) never contacts a scanner: covered by every other upload test


def test_postgres_refuses_to_change_or_delete_audit_history(client, db, clinic):
    """The append-only trigger (PostgreSQL only; SQLite has the signatures above)."""
    from sqlalchemy import delete
    from sqlalchemy.exc import DBAPIError

    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("append-only trigger exists on PostgreSQL only")
    clinic.post("/customers", {"full_name": "Kept Forever", "mobile": "9811122299"})
    row_id = _audit(db, "customer.created")[-1].id
    for stmt in (update(AuditLog).where(AuditLog.id == row_id).values(action="x"), delete(AuditLog).where(AuditLog.id == row_id)):
        nested = db.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(stmt)
        nested.rollback()


def test_watermark_policy_has_no_personal_data_and_print_attempts_are_recorded(client, db, clinic):
    pol = clinic.client.get("/api/v1/users/me/privacy", headers=clinic.h)
    assert pol.status_code == 200, pol.text
    body = pol.json()
    assert body["user_ref"].startswith("U-") and body["session_ref"].startswith("S-") and body["print_policy"] == "warn"
    assert "priv-owner" not in str(body) and "@" not in str(body)  # references only: no name, email or number
    r = clinic.client.post("/api/v1/users/me/privacy/print-attempt", json={"screen": "/admin/customers/abc?search=ramesh#x"}, headers=clinic.h)
    assert r.status_code == 200, r.text
    row = _audit(db, "privacy.print_attempt")[-1]
    assert row.entity_id == "/admin/customers/abc" and row.after == {"policy": "warn"}  # the search term is never stored
    assert client.post("/api/v1/users/me/privacy/print-attempt", json={"screen": "/x"}).status_code == 401
