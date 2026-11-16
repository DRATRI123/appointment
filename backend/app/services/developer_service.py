"""API keys, webhook endpoints, the webhook outbox and its delivery worker.

Webhooks: domain changes write one ``webhook_events`` row per subscribed endpoint in the same transaction
(outbox), so a rolled-back booking never fires an event. The worker signs and POSTs each row, retrying with
backoff (1 m, 5 m, 30 m, 2 h, 6 h, 12 h, 24 h). An endpoint that fails 50 deliveries in a row is switched off.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import WebhookDeliveryStatus as W
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError, request
from app.models import APIKey, ApiKeyUsage, Organization, User, WebhookEndpoint, WebhookEvent
from app.schemas.developer import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    DeliveryDetail,
    DeliveryRead,
    OrgApiUsage,
    UsageDay,
    WebhookCreate,
    WebhookCreated,
    WebhookRead,
    WebhookUpdate,
)
from app.security import api_keys as ak
from app.security.crypto import decrypt_text, encrypt_text
from app.services.audit_service import RequestMeta, record_audit
from app.webhooks.catalog import API_VERSION, EVENTS
from app.webhooks.security import SIGNATURE_HEADER, check_url, sign

log = get_logger(__name__)
BACKOFF_MINUTES = [1, 5, 30, 120, 360, 720, 1440]
DISABLE_AFTER = 50
MAX_ENDPOINTS = 20
MAX_KEYS = 25


class DeveloperService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None, *, actor_permissions: set[str] | None = None):
        self.db, self.org, self.actor, self.meta = db, org, actor, meta or RequestMeta()
        self.actor_permissions = actor_permissions or set()

    def _audit(self, action: str, entity_type: str, entity_id: str, **kw) -> None:
        record_audit(self.db, action=action, actor=self.actor, organization_id=self.org.id, entity_type=entity_type, entity_id=entity_id, meta=self.meta, **kw)

    # ================================================================ API keys
    def key(self, public_id: str) -> APIKey:
        k = self.db.scalar(select(APIKey).where(APIKey.public_id == public_id, APIKey.organization_id == self.org.id))
        if k is None:
            raise NotFoundError("API key not found.")
        return k

    def key_read(self, k: APIKey) -> ApiKeyRead:
        creator = self.db.get(User, k.created_by_user_id) if k.created_by_user_id else None
        since = (utcnow() - timedelta(days=30)).date()
        used = self.db.scalar(select(func.coalesce(func.sum(ApiKeyUsage.requests), 0)).where(ApiKeyUsage.api_key_id == k.id, ApiKeyUsage.day >= since)) or 0
        configured = (k.rate_limit or "").split("/")[0]
        return ApiKeyRead(id=k.public_id, name=k.name, prefix=k.key_prefix, scopes=list(k.scopes or []), allowed_ips=list(k.allowed_ips or []),
                          rate_limit_per_minute=int(configured) if configured.isdigit() else get_settings().api_key_default_rate_limit,
                          expires_at=k.expires_at, last_used_at=k.last_used_at, revoked_at=k.revoked_at, is_active=k.is_active and k.revoked_at is None,
                          created_by_name=creator.full_name if creator else None, created_at=k.created_at, requests_30d=int(used))

    def keys(self) -> list[APIKey]:
        return list(self.db.scalars(select(APIKey).where(APIKey.organization_id == self.org.id).order_by(APIKey.revoked_at.is_not(None), APIKey.created_at.desc())).all())

    def create_key(self, payload: ApiKeyCreate) -> ApiKeyCreated:
        unknown = [s for s in payload.scopes if s not in ak.API_SCOPES]
        if unknown:
            raise ValidationFailed(f"These scopes cannot be given to API keys: {', '.join(unknown)}", code="invalid_scope")
        beyond = [s for s in payload.scopes if s not in self.actor_permissions]
        if beyond:
            raise PermissionDenied(f"You can only grant scopes you have yourself. Missing: {', '.join(beyond)}", code="scope_exceeds_yours")
        if payload.expires_at and payload.expires_at <= utcnow():
            raise ValidationFailed("The expiry date must be in the future.", code="invalid_expiry")
        active = self.db.scalar(select(func.count()).select_from(APIKey).where(APIKey.organization_id == self.org.id, APIKey.revoked_at.is_(None))) or 0
        if active >= MAX_KEYS:
            raise ConflictError(f"An organization can have at most {MAX_KEYS} active keys. Revoke unused keys first.", code="too_many_keys")
        plaintext, prefix = ak.generate()
        k = APIKey(organization_id=self.org.id, name=payload.name.strip(), key_prefix=prefix, key_hash=ak.hash_key(plaintext), scopes=sorted(set(payload.scopes)),
                   created_by_user_id=self.actor.id if self.actor else None, expires_at=payload.expires_at, allowed_ips=payload.allowed_ips or None,
                   rate_limit=f"{payload.rate_limit_per_minute}/minute" if payload.rate_limit_per_minute else None, is_active=True)
        self.db.add(k)
        self.db.flush()
        self._audit("api_key.created", "api_key", k.public_id, after={"name": k.name, "prefix": prefix, "scopes": k.scopes, "expires_at": str(k.expires_at) if k.expires_at else None})
        return ApiKeyCreated(**self.key_read(k).model_dump(), key=plaintext)

    def revoke_key(self, k: APIKey) -> APIKey:
        if k.revoked_at is None:
            k.revoked_at, k.is_active = utcnow(), False
            self._audit("api_key.revoked", "api_key", k.public_id, before={"name": k.name, "prefix": k.key_prefix})
        return k

    def rotate_key(self, k: APIKey, grace_hours: int = 24) -> ApiKeyCreated:
        """A new key with the same name, scopes, IP list, rate limit and expiry. The old key keeps working for
        ``grace_hours`` (0 = stops now) so integrations can be switched without downtime."""
        if k.revoked_at is not None or not k.is_active:
            raise ConflictError("This key is revoked. Create a new key instead.", code="key_revoked")
        if not 0 <= grace_hours <= 168:
            raise ValidationFailed("The overlap must be between 0 and 168 hours.", code="invalid_grace")
        configured = (k.rate_limit or "").split("/")[0]
        new = self.create_key(ApiKeyCreate(name=k.name, scopes=list(k.scopes or []), allowed_ips=list(k.allowed_ips or []),
                                           expires_at=k.expires_at if k.expires_at and k.expires_at > utcnow() else None,
                                           rate_limit_per_minute=int(configured) if configured.isdigit() else None))
        stop = utcnow() + timedelta(hours=grace_hours)
        if grace_hours == 0:
            k.revoked_at, k.is_active = utcnow(), False
        elif k.expires_at is None or k.expires_at > stop:
            k.expires_at = stop
        self._audit("api_key.rotated", "api_key", k.public_id, after={"new_key": new.id, "old_key_valid_until": stop.isoformat()})
        return new

    def access_logs(self, k: APIKey, limit: int = 100) -> list[dict]:
        from app.models import ApiAccessLog

        rows = self.db.scalars(select(ApiAccessLog).where(ApiAccessLog.api_key_id == k.id).order_by(ApiAccessLog.id.desc()).limit(limit)).all()
        return [{"method": r.method, "path": r.path, "status": r.status_code, "duration_ms": r.duration_ms, "ip": r.ip_address, "at": r.created_at} for r in rows]

    def usage(self, k: APIKey, days: int = 30) -> list[UsageDay]:
        since = (utcnow() - timedelta(days=days - 1)).date()
        rows = {r.day: r for r in self.db.scalars(select(ApiKeyUsage).where(ApiKeyUsage.api_key_id == k.id, ApiKeyUsage.day >= since)).all()}
        out = []
        for i in range(days):
            d = since + timedelta(days=i)
            r = rows.get(d)
            out.append(UsageDay(day=d, requests=r.requests if r else 0, client_errors=r.client_errors if r else 0, server_errors=r.server_errors if r else 0,
                                rate_limited=r.rate_limited if r else 0))
        return out

    # ================================================================ webhooks
    def endpoint(self, public_id: str) -> WebhookEndpoint:
        e = self.db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.public_id == public_id, WebhookEndpoint.organization_id == self.org.id))
        if e is None:
            raise NotFoundError("Webhook endpoint not found.")
        return e

    def endpoints(self) -> list[WebhookEndpoint]:
        return list(self.db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.organization_id == self.org.id).order_by(WebhookEndpoint.created_at)).all())

    def endpoint_read(self, e: WebhookEndpoint) -> WebhookRead:
        since = utcnow() - timedelta(days=7)
        counts = dict(self.db.execute(select(WebhookEvent.status, func.count()).where(WebhookEvent.endpoint_id == e.id, WebhookEvent.created_at >= since)
                                      .group_by(WebhookEvent.status)).all())
        return WebhookRead(id=e.public_id, name=e.name, url=e.url, events=list(e.events or []), is_active=e.is_active, api_version=e.api_version, failure_count=e.failure_count,
                           disabled_at=e.disabled_at, created_at=e.created_at, delivered_7d=int(counts.get(W.DELIVERED, 0)),
                           failed_7d=int(counts.get(W.DEAD, 0) + counts.get(W.FAILED, 0)))

    @staticmethod
    def _check_events(events: list[str]) -> list[str]:
        bad = [e for e in events if e not in EVENTS or e == "ping"] if "*" not in events else []
        if bad:
            raise ValidationFailed(f"Unknown events: {', '.join(bad)}", code="unknown_event")
        return ["*"] if "*" in events else sorted(set(events))

    @staticmethod
    def _check_url(url: str) -> str:
        url = url.strip()
        reason = check_url(url)
        if reason:
            raise ValidationFailed(reason, code="invalid_webhook_url")
        return url

    def create_endpoint(self, payload: WebhookCreate) -> WebhookCreated:
        if len(self.endpoints()) >= MAX_ENDPOINTS:
            raise ConflictError(f"At most {MAX_ENDPOINTS} webhook endpoints per organization.", code="too_many_endpoints")
        secret = "whsec_" + secrets.token_urlsafe(32)
        e = WebhookEndpoint(organization_id=self.org.id, name=payload.name.strip(), url=self._check_url(payload.url), secret_encrypted=encrypt_text(secret),
                            events=self._check_events(payload.events), is_active=payload.is_active, api_version=API_VERSION, created_by_user_id=self.actor.id if self.actor else None)
        self.db.add(e)
        self.db.flush()
        self._audit("webhook.created", "webhook_endpoint", e.public_id, after={"url": e.url, "events": e.events})
        return WebhookCreated(**self.endpoint_read(e).model_dump(), secret=secret)

    def update_endpoint(self, e: WebhookEndpoint, payload: WebhookUpdate) -> WebhookEndpoint:
        before = {"url": e.url, "events": e.events, "is_active": e.is_active}
        if payload.name is not None:
            e.name = payload.name.strip()
        if payload.url is not None:
            e.url = self._check_url(payload.url)
        if payload.events is not None:
            e.events = self._check_events(payload.events)
        if payload.is_active is not None:
            e.is_active = payload.is_active
            if payload.is_active:
                e.disabled_at, e.failure_count = None, 0
        self._audit("webhook.updated", "webhook_endpoint", e.public_id, before=before, after={"url": e.url, "events": e.events, "is_active": e.is_active})
        return e

    def rotate_secret(self, e: WebhookEndpoint) -> str:
        secret = "whsec_" + secrets.token_urlsafe(32)
        e.secret_encrypted = encrypt_text(secret)
        self._audit("webhook.secret_rotated", "webhook_endpoint", e.public_id)
        return secret

    def delete_endpoint(self, e: WebhookEndpoint) -> None:
        self._audit("webhook.deleted", "webhook_endpoint", e.public_id, before={"url": e.url})
        self.db.delete(e)

    def ping(self, e: WebhookEndpoint) -> WebhookEvent:
        ev = _event_row(self.org, e, "ping", {"message": "Test event from the developer portal.", "endpoint": e.public_id})
        self.db.add(ev)
        self.db.flush()
        deliver(self.db, ev)
        return ev

    def deliveries(self, e: WebhookEndpoint, *, status: str | None, page: int, page_size: int) -> tuple[list[WebhookEvent], int]:
        stmt = select(WebhookEvent).where(WebhookEvent.endpoint_id == e.id)
        if status:
            stmt = stmt.where(WebhookEvent.status.in_(status.split(",")))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(WebhookEvent.created_at.desc(), WebhookEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    def delivery(self, public_id: str) -> WebhookEvent:
        ev = self.db.scalar(select(WebhookEvent).where(WebhookEvent.public_id == public_id, WebhookEvent.organization_id == self.org.id))
        if ev is None:
            raise NotFoundError("Delivery not found.")
        return ev

    def redeliver(self, ev: WebhookEvent) -> WebhookEvent:
        ev.status, ev.next_attempt_at, ev.last_error = W.PENDING, utcnow(), None
        ev.attempts = 0
        self._audit("webhook.redelivered", "webhook_event", ev.public_id)
        return ev

    @staticmethod
    def delivery_read(ev: WebhookEvent, detail: bool = False):
        base = dict(id=ev.public_id, event_id=ev.event_id, event=ev.event_name, status=ev.status, attempts=ev.attempts, response_status=ev.response_status,
                    last_error=ev.last_error, next_attempt_at=ev.next_attempt_at, last_attempt_at=ev.last_attempt_at, created_at=ev.created_at)
        return DeliveryDetail(**base, payload=ev.payload, response_body=ev.response_body) if detail else DeliveryRead(**base)


# ==================================================================== outbox
def _event_row(org: Organization, endpoint: WebhookEndpoint, name: str, data: dict[str, Any], event_id: str | None = None) -> WebhookEvent:
    eid = event_id or f"evt_{new_ulid()}"
    payload = {"id": eid, "type": name, "api_version": endpoint.api_version or API_VERSION, "created_at": utcnow().isoformat(),
               "organization": {"id": org.public_id, "slug": org.slug}, "data": data}
    return WebhookEvent(organization_id=org.id, endpoint_id=endpoint.id, event_name=name, event_id=eid[:36], payload=payload, status=W.PENDING, next_attempt_at=utcnow())


def emit(db: Session, org: Organization, name: str, data_fn) -> int:
    """Queue an event for every active endpoint subscribed to it. ``data_fn`` is only called when someone listens.
    Never raises into the business transaction."""
    try:
        with db.begin_nested():
            endpoints = [e for e in db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.organization_id == org.id, WebhookEndpoint.is_active.is_(True))).all()
                         if "*" in (e.events or []) or name in (e.events or [])]
            if not endpoints:
                return 0
            data = data_fn()
            eid = f"evt_{new_ulid()}"
            for e in endpoints:
                db.add(_event_row(org, e, name, data, eid))
            db.flush()
            return len(endpoints)
    except Exception:  # noqa: BLE001
        log.exception("webhook.emit_failed", event=name, organization=org.id)
        return 0


def deliver(db: Session, ev: WebhookEvent) -> bool:
    endpoint = db.get(WebhookEndpoint, ev.endpoint_id)
    now = utcnow()
    ev.last_attempt_at = now
    ev.attempts = (ev.attempts or 0) + (0 if ev.status == "sending" else 1)
    if endpoint is None:
        ev.status, ev.last_error = W.DEAD, "endpoint deleted"
        return False
    if not endpoint.is_active and ev.event_name != "ping":
        ev.status, ev.last_error = W.DEAD, "endpoint is switched off"
        return False
    body = json.dumps(ev.payload, separators=(",", ":"), ensure_ascii=False).encode()
    ts = int(time.time())
    headers = {"Content-Type": "application/json", "User-Agent": "AppointmentPlatform-Webhooks/1.0", "X-Webhook-Id": ev.event_id, "X-Webhook-Event": ev.event_name,
               "X-Webhook-Timestamp": str(ts), SIGNATURE_HEADER: sign(decrypt_text(endpoint.secret_encrypted), ts, body)}
    reason = check_url(endpoint.url)  # re-checked at send time (DNS may have changed)
    ok = False
    if reason:
        ev.response_status, ev.response_body, ev.last_error = None, None, f"Blocked: {reason}"
    else:
        try:
            resp = request("POST", endpoint.url, content=body, headers=headers, timeout=get_settings().webhook_timeout_seconds, follow_redirects=False)
            ev.response_status, ev.response_body = resp.status_code, resp.text[:1000]
            ok = 200 <= resp.status_code < 300
            ev.last_error = None if ok else f"HTTP {resp.status_code}"
        except IntegrationAPIError as exc:
            ev.response_status, ev.response_body, ev.last_error = None, None, str(exc)[:500]
    if ok:
        ev.status, ev.next_attempt_at = W.DELIVERED, None
        endpoint.failure_count = 0
        return True
    endpoint.failure_count = (endpoint.failure_count or 0) + 1
    if endpoint.failure_count >= DISABLE_AFTER and endpoint.is_active:
        endpoint.is_active, endpoint.disabled_at = False, now
        record_audit(db, action="webhook.auto_disabled", actor=None, organization_id=endpoint.organization_id, entity_type="webhook_endpoint",
                     entity_id=endpoint.public_id, after={"failures": endpoint.failure_count})
    if ev.event_name == "ping" or ev.attempts >= get_settings().webhook_max_attempts:
        ev.status, ev.next_attempt_at = (W.FAILED if ev.event_name == "ping" else W.DEAD), None
    else:
        ev.status = W.RETRYING
        ev.next_attempt_at = now + timedelta(minutes=BACKOFF_MINUTES[min(ev.attempts - 1, len(BACKOFF_MINUTES) - 1)])
    return False


def deliver_due(db: Session, *, limit: int = 100, commit: bool = True) -> dict[str, int]:
    now = utcnow()
    db.execute(update(WebhookEvent).where(WebhookEvent.status == "sending", WebhookEvent.updated_at < now - timedelta(minutes=10)).values(status=W.RETRYING))
    ids = db.scalars(select(WebhookEvent.id).where(WebhookEvent.status.in_([W.PENDING, W.RETRYING]), WebhookEvent.next_attempt_at <= now)
                     .order_by(WebhookEvent.next_attempt_at, WebhookEvent.id).limit(limit)).all()
    counts = {"delivered": 0, "retrying": 0, "dead": 0}
    for eid in ids:
        claimed = db.execute(update(WebhookEvent).where(WebhookEvent.id == eid, WebhookEvent.status.in_([W.PENDING, W.RETRYING]))
                             .values(status="sending", attempts=WebhookEvent.attempts + 1, updated_at=utcnow())).rowcount
        if not claimed:
            continue
        ev = db.get(WebhookEvent, eid)
        db.refresh(ev)
        deliver(db, ev)
        counts["delivered" if ev.status == W.DELIVERED else "retrying" if ev.status == W.RETRYING else "dead"] += 1
        if commit:
            db.commit()
        else:
            db.flush()
    return counts


def purge_old_deliveries(db: Session, days: int = 30) -> int:
    cutoff = utcnow() - timedelta(days=days)
    return db.query(WebhookEvent).filter(WebhookEvent.status.in_([W.DELIVERED, W.DEAD, W.FAILED]), WebhookEvent.created_at < cutoff).delete(synchronize_session=False)


# ==================================================================== usage
def record_usage(db: Session, key_id: int, org_id: int, status_code: int, rate_limited: bool, request=None, duration_ms: int | None = None) -> None:
    today = datetime.now(UTC).date()
    if request is not None:  # access log: method, route template (never query strings), status, time, address
        from app.models import ApiAccessLog

        route = request.scope.get("route")
        template = getattr(route, "path", None)
        prefix = get_settings().api_v1_prefix
        path = (template if template.startswith(prefix) else f"{prefix}{template}") if template else request.url.path
        db.add(ApiAccessLog(organization_id=org_id, api_key_id=key_id, method=request.method[:8], path=str(path)[:255], status_code=status_code,
                            duration_ms=duration_ms, ip_address=(request.client.host if request.client else None), created_at=utcnow()))
    row = db.scalar(select(ApiKeyUsage).where(ApiKeyUsage.api_key_id == key_id, ApiKeyUsage.day == today))
    if row is None:
        row = ApiKeyUsage(organization_id=org_id, api_key_id=key_id, day=today, requests=0, client_errors=0, server_errors=0, rate_limited=0)
        db.add(row)
    row.requests += 1
    if rate_limited:
        row.rate_limited += 1
    elif 400 <= status_code < 500:
        row.client_errors += 1
    elif status_code >= 500:
        row.server_errors += 1


def platform_usage(db: Session, days: int) -> list[OrgApiUsage]:
    since_day: date = (utcnow() - timedelta(days=days - 1)).date()
    since = utcnow() - timedelta(days=days)
    usage = {oid: (r, ce + se, rl) for oid, r, ce, se, rl in db.execute(select(ApiKeyUsage.organization_id, func.sum(ApiKeyUsage.requests), func.sum(ApiKeyUsage.client_errors),
                                                                                   func.sum(ApiKeyUsage.server_errors), func.sum(ApiKeyUsage.rate_limited))
                                                                            .where(ApiKeyUsage.day >= since_day).group_by(ApiKeyUsage.organization_id)).all()}
    keys = dict(db.execute(select(APIKey.organization_id, func.count()).where(APIKey.revoked_at.is_(None)).group_by(APIKey.organization_id)).all())
    eps = dict(db.execute(select(WebhookEndpoint.organization_id, func.count()).group_by(WebhookEndpoint.organization_id)).all())
    eps_off = dict(db.execute(select(WebhookEndpoint.organization_id, func.count()).where(WebhookEndpoint.disabled_at.is_not(None)).group_by(WebhookEndpoint.organization_id)).all())
    deliv: dict[int, dict[str, int]] = {}
    for oid, st, n in db.execute(select(WebhookEvent.organization_id, WebhookEvent.status, func.count()).where(WebhookEvent.created_at >= since)
                                 .group_by(WebhookEvent.organization_id, WebhookEvent.status)).all():
        deliv.setdefault(oid, {})[st] = n
    org_ids = set(usage) | set(keys) | set(eps)
    orgs = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids))).all()} if org_ids else {}
    out = []
    for oid in org_ids:
        o = orgs.get(oid)
        if o is None:
            continue
        r, err, rl = usage.get(oid, (0, 0, 0))
        d = deliv.get(oid, {})
        out.append(OrgApiUsage(organization_id=o.public_id, organization_name=o.name, active_keys=int(keys.get(oid, 0)), requests=int(r or 0), errors=int(err or 0),
                               rate_limited=int(rl or 0), endpoints=int(eps.get(oid, 0)), endpoints_disabled=int(eps_off.get(oid, 0)),
                               deliveries_ok=int(d.get(W.DELIVERED, 0)), deliveries_failed=int(d.get(W.DEAD, 0) + d.get(W.FAILED, 0) + d.get(W.RETRYING, 0))))
    return sorted(out, key=lambda x: (-x.requests, x.organization_name))
