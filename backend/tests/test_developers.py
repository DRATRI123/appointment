from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.integrations import http as integration_http
from app.models import APIKey, ApiKeyUsage, AuditLog, OrganizationMembership, Role, User, WebhookEndpoint, WebhookEvent
from app.security import api_keys as ak
from app.services.developer_service import DISABLE_AFTER, deliver_due
from app.webhooks.security import check_url, verify
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, register
from tests.test_payments import _verifier


@pytest.fixture(autouse=True)
def _reset_limiter():
    ak.limiter.reset()
    yield
    ak.limiter.reset()


def _key(client, c: Clinic, scopes, expect=201, **extra):
    r = client.post("/api/v1/developers/api-keys", json={"name": "Integration", "scopes": scopes, **extra}, headers=c.h)
    assert r.status_code == expect, r.text
    return r.json()


def test_api_keys_scopes_paths_limits_and_revocation(client, db, monkeypatch):
    c = Clinic(client, email="dev-owner@example.com", name="Dev Clinic", payment_mode="pay_at_clinic")
    c.staff_book(ist(c.monday, 9), customer={"full_name": "Api Guest", "mobile": "9870000001"})
    assert _key(client, c, ["payments:verify"], expect=422)["code"] == "invalid_scope"
    created = _key(client, c, ["appointments:read", "customers:read", "reports:read"])
    raw = created["key"]
    assert raw.startswith("ak_live_") and created["prefix"] == raw[:16] and "key" not in client.get("/api/v1/developers/api-keys", headers=c.h).json()[0]
    row = db.scalar(select(APIKey).where(APIKey.public_id == created["id"]))
    assert row.key_hash != raw and raw not in json.dumps(row.to_dict(), default=str)
    k = {"Authorization": f"Bearer {raw}"}
    client.cookies.clear()

    # Reads within scope work, with either header; the organization comes from the key.
    appts = client.get("/api/v1/appointments", headers=k)
    assert appts.status_code == 200 and appts.json()[0]["customer"]["full_name"] == "Api Guest"
    assert client.get("/api/v1/customers", headers={"X-API-Key": raw}).status_code == 200
    # Writes outside scope, and paths keys may never touch.
    r = client.post(f"/api/v1/appointments/{appts.json()[0]['id']}/status", json={"action": "cancel"}, headers=k)
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    for path in ("/api/v1/users/me", "/api/v1/auth/sessions", "/api/v1/developers/api-keys", "/api/v1/platform/stats", "/api/v1/customer/payments", f"/api/v1/organizations/{c.org['id']}/members", "/api/v1/me/notifications"):
        resp = client.get(path, headers=k)
        assert resp.status_code == 403 and resp.json()["code"] == "api_key_not_allowed", path
    other = Clinic(client, email="dev-other@example.com", name="Other Dev")
    client.cookies.clear()
    r = client.get("/api/v1/appointments", headers={**k, "X-Organization-Id": other.org["id"]})
    assert r.status_code == 403 and r.json()["code"] == "wrong_organization"
    assert client.get("/api/v1/appointments", headers={"Authorization": "Bearer ak_live_deadbeef_nope"}).json()["code"] == "invalid_api_key"

    # Effective permissions = scopes ∩ the creator's current role: demote the creator and reports stop.
    assert client.get("/api/v1/reports/daily_summary", headers=k).status_code == 200
    membership = db.scalar(select(OrganizationMembership).join(User, User.id == OrganizationMembership.user_id).where(User.email == "dev-owner@example.com"))
    owner_role = membership.role_id
    membership.role_id = db.scalar(select(Role.id).where(Role.code == "receptionist", Role.organization_id.is_(None)))
    db.flush()
    db.expire(membership)
    assert client.get("/api/v1/reports/daily_summary", headers=k).status_code == 403
    membership.status = "removed"
    db.flush()
    assert client.get("/api/v1/appointments", headers=k).json()["code"] == "api_key_owner_removed"
    membership.status, membership.role_id = "active", owner_role
    db.flush()
    db.expire(membership)  # drop the cached role relationship (each real request uses a fresh session)

    # Per-key rate limit with Retry-After; usage is counted per day.
    limited = _key(client, c, ["appointments:read"], rate_limit_per_minute=2)
    client.cookies.clear()
    lk = {"Authorization": f"Bearer {limited['key']}"}
    assert [client.get("/api/v1/appointments", headers=lk).status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/api/v1/appointments", headers=lk).headers["retry-after"].isdigit()
    usage = db.scalar(select(ApiKeyUsage).where(ApiKeyUsage.api_key_id == db.scalar(select(APIKey.id).where(APIKey.public_id == limited["id"]))))
    assert usage.requests == 4 and usage.rate_limited == 2
    assert client.get(f"/api/v1/developers/api-keys/{limited['id']}/usage", params={"days": 7}, headers=c.h).json()[-1]["requests"] == 4

    # IP allowlist honours X-Forwarded-For only from trusted proxies.
    ipk = _key(client, c, ["appointments:read"], allowed_ips=["10.0.0.0/8"])
    assert _key(client, c, ["appointments:read"], allowed_ips=["not-an-ip"], expect=422)
    client.cookies.clear()
    spoofed = client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {ipk['key']}", "X-Forwarded-For": "10.1.2.3"})
    assert spoofed.status_code == 403 and spoofed.json()["code"] == "ip_not_allowed"
    monkeypatch.setattr(get_settings(), "forwarded_allow_ips", ["testclient"])
    assert client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {ipk['key']}", "X-Forwarded-For": "10.1.2.3"}).status_code == 200

    # Expiry and revocation take effect immediately.
    assert _key(client, c, ["appointments:read"], expires_at=(utcnow() - timedelta(days=1)).isoformat(), expect=422)["code"] == "invalid_expiry"
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/v1/appointments", headers=k).json()["code"] == "invalid_api_key"
    revoked = client.delete(f"/api/v1/developers/api-keys/{limited['id']}", headers=c.h).json()
    assert revoked["is_active"] is False and client.get("/api/v1/appointments", headers=lk).status_code == 401
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.action.like("api_key.%"))).all())
    assert {"api_key.created", "api_key.revoked"} <= actions

    # Only members with api_keys:manage reach the portal; other organizations see nothing.
    rec = _verifier(client, c, role="receptionist", mobile="9600000071")
    assert client.get("/api/v1/developers/api-keys", headers=rec).status_code == 403
    assert other.get("/developers/api-keys") == []


class Receiver:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.url.path == "/fail":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"ok": True})


def test_webhooks_outbox_signature_retries_and_disable(client, db):
    rx = Receiver()
    integration_http.set_http_client(httpx.Client(transport=httpx.MockTransport(rx)))
    try:
        c = Clinic(client, email="wh-owner@example.com", name="Hook Clinic", payment_mode="pay_at_clinic")
        assert client.post("/api/v1/developers/webhooks", json={"name": "Bad", "url": "https://hooks.example.com/ok", "events": ["appointment.nope"]}, headers=c.h).json()["code"] == "unknown_event"
        assert client.post("/api/v1/developers/webhooks", json={"name": "Bad", "url": "ftp://hooks.example.com", "events": ["*"]}, headers=c.h).json()["code"] == "invalid_webhook_url"
        ep = c.post("/developers/webhooks", {"name": "CRM", "url": "https://hooks.example.com/ok", "events": ["appointment.created", "appointment.cancelled", "payment.verified"]})
        secret = ep["secret"]
        assert secret.startswith("whsec_") and "secret" not in c.get("/developers/webhooks")[0]
        stored = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.public_id == ep["id"]))
        assert secret not in stored.secret_encrypted

        appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Hook Guest", "mobile": "9870000101"})
        assert [e.event_name for e in db.scalars(select(WebhookEvent)).all()] == ["appointment.created"]  # confirmed not subscribed
        assert deliver_due(db, commit=False)["delivered"] == 1
        req = rx.requests[-1]
        body = req.content
        assert verify(secret, req.headers["x-webhook-signature"], body, now=int(req.headers["x-webhook-timestamp"]))
        assert not verify(secret, req.headers["x-webhook-signature"], body + b" ", now=int(req.headers["x-webhook-timestamp"]))
        payload = json.loads(body)
        assert payload["type"] == "appointment.created" and payload["data"]["reference"] == appt["reference"] and payload["data"]["customer"]["name"] == "Hook Guest"
        assert req.headers["x-webhook-event"] == "appointment.created" and req.headers["x-webhook-id"] == payload["id"] and "internal_notes" not in body.decode()

        client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h)
        deliver_due(db, commit=False)
        assert json.loads(rx.requests[-1].content)["type"] == "appointment.cancelled"

        # A failing endpoint retries with backoff, then gives up; enough failures switch it off.
        bad = c.post("/developers/webhooks", {"name": "Flaky", "url": "https://hooks.example.com/fail", "events": ["*"]})
        appt2 = c.staff_book(ist(c.monday, 10), customer={"full_name": "Second", "mobile": "9870000102"})
        counts = deliver_due(db, commit=False)
        # customer.created + appointment.created + appointment.confirmed to Flaky fail; appointment.created to CRM ok
        assert counts["retrying"] == 3 and counts["delivered"] == 1
        ev = db.scalar(select(WebhookEvent).join(WebhookEndpoint).where(WebhookEndpoint.public_id == bad["id"], WebhookEvent.event_name == "appointment.created"))
        assert ev.status == "retrying" and ev.attempts == 1 and ev.response_status == 500 and ev.next_attempt_at > utcnow()
        ev.attempts = get_settings().webhook_max_attempts - 1
        ev.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.flush()
        deliver_due(db, commit=False)
        db.refresh(ev)
        assert ev.status == "dead"
        page = c.get(f"/developers/webhooks/{bad['id']}/deliveries")
        assert page["meta"]["total"] == 3 and {d["status"] for d in page["data"]} == {"dead", "retrying"}
        assert c.post(f"/developers/deliveries/{ev.public_id}/redeliver", {}, expect=200)["status"] == "pending"
        flaky = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.public_id == bad["id"]))
        flaky.failure_count = DISABLE_AFTER - 1
        ev.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.flush()
        deliver_due(db, commit=False)
        db.refresh(flaky)
        assert flaky.is_active is False and flaky.disabled_at is not None
        assert c.get("/developers/webhooks")[1]["is_active"] is False
        client.patch(f"/api/v1/developers/webhooks/{bad['id']}", json={"is_active": True}, headers=c.h)
        db.refresh(flaky)
        assert flaky.is_active and flaky.failure_count == 0

        # Test ping, secret rotation, payment events, isolation and permissions.
        ping = c.post(f"/developers/webhooks/{ep['id']}/test", {}, expect=200)
        assert ping["status"] == "delivered" and ping["response_status"] == 200 and ping["payload"]["type"] == "ping"
        new_secret = c.post(f"/developers/webhooks/{ep['id']}/rotate-secret", {}, expect=200)["detail"]
        c.post(f"/developers/webhooks/{ep['id']}/test", {}, expect=200)
        last = rx.requests[-1]
        assert verify(new_secret, last.headers["x-webhook-signature"], last.content, now=int(last.headers["x-webhook-timestamp"]))
        assert not verify(secret, last.headers["x-webhook-signature"], last.content, now=int(last.headers["x-webhook-timestamp"]))
        assert {e["name"] for e in c.get("/developers/events")} >= {"appointment.created", "payment.verified", "refund.processed", "ping"}
        other = Clinic(client, email="wh-other@example.com", name="Other Hook")
        assert client.get(f"/api/v1/developers/webhooks/{ep['id']}/deliveries", headers=other.h).status_code == 404
        assert client.post(f"/api/v1/developers/deliveries/{ev.public_id}/redeliver", headers=other.h).status_code == 404
        client.patch(f"/api/v1/developers/webhooks/{ep['id']}", json={"is_active": False}, headers=c.h)
        before = db.scalar(select(WebhookEvent.id).order_by(WebhookEvent.id.desc()))
        client.post(f"/api/v1/appointments/{appt2['id']}/status", json={"action": "cancel"}, headers=c.h)
        assert db.scalars(select(WebhookEvent).where(WebhookEvent.id > before, WebhookEvent.endpoint_id == stored.id)).all() == []
        assert client.delete(f"/api/v1/developers/webhooks/{bad['id']}", headers=c.h).status_code == 200
    finally:
        integration_http.set_http_client(None)


def test_ssrf_guard(monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_allow_private_targets", False)
    resolve = lambda ips: (lambda host, port: ips)  # noqa: E731
    assert check_url("http://hooks.example.com/x", resolver=resolve(["93.184.216.34"])) == "Webhook URLs must use https."
    assert check_url("https://user:pw@hooks.example.com/x") == "Do not put credentials in the URL."
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1", "fd00::1", "0.0.0.0"):
        assert check_url("https://internal.example/x", resolver=resolve([ip])) == "Webhook URLs must point to a public internet address.", ip
    assert check_url("https://hooks.example.com/x", resolver=resolve(["93.184.216.34", "10.0.0.1"])) is not None  # any private answer blocks
    assert check_url("https://hooks.example.com/x", resolver=resolve(["93.184.216.34"])) is None


def test_platform_api_usage(client, db):
    c = Clinic(client, email="use-owner@example.com", name="Usage Clinic")
    key = _key(client, c, ["appointments:read"])["key"]
    client.cookies.clear()
    client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {key}"})
    root = register(client, "api-root@example.com", "Root")
    client.cookies.clear()
    db.scalar(select(User).where(User.email == "api-root@example.com")).is_platform_admin = True
    db.flush()
    rows = client.get("/api/v1/platform/api-usage", headers=bearer(root)).json()
    mine = next(r for r in rows if r["organization_name"] == "Usage Clinic")
    assert mine["requests"] == 1 and mine["active_keys"] == 1
    assert client.get("/api/v1/platform/api-usage", headers=c.h).status_code == 403
