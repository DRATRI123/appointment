"""Developer portal: API keys, webhook endpoints, delivery logs and the event catalogue (``api_keys:manage``)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, Meta, TenantContext, recent_auth, require_permission
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.schemas.common import Message
from app.schemas.developer import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    DeliveryDetail,
    DeliveryRead,
    EventInfo,
    ScopeInfo,
    UsageDay,
    WebhookCreate,
    WebhookCreated,
    WebhookRead,
    WebhookUpdate,
)
from app.security.api_keys import API_SCOPES
from app.services.developer_service import DeveloperService
from app.webhooks.catalog import API_VERSION, EVENTS

router = APIRouter(prefix="/developers", tags=["developers"])
Manage = Annotated[TenantContext, Depends(require_permission("api_keys:manage"))]


def _svc(db, ctx: TenantContext, meta) -> DeveloperService:
    return DeveloperService(db, ctx.organization, ctx.user, meta, actor_permissions=ctx.permissions if not ctx.is_platform_admin else set(API_SCOPES))


@router.get("/scopes", response_model=list[ScopeInfo], summary="Scopes an API key can hold")
def scopes(ctx: Manage):
    return [ScopeInfo(code=c, description=d, you_have_it=ctx.has(c)) for c, d in API_SCOPES.items()]


@router.get("/api-keys", response_model=list[ApiKeyRead])
def list_keys(db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return [svc.key_read(k) for k in svc.keys()]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED, dependencies=[recent_auth("api_keys")], summary="Create a key (the secret is returned once)")
def create_key(payload: ApiKeyCreate, db: DB, ctx: Manage, meta: Meta):
    return _svc(db, ctx, meta).create_key(payload)


@router.get("/api-keys/{key_id}/usage", response_model=list[UsageDay])
def key_usage(key_id: str, db: DB, ctx: Manage, meta: Meta, days: Annotated[int, Query(ge=1, le=90)] = 30):
    svc = _svc(db, ctx, meta)
    return svc.usage(svc.key(key_id), days)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRead, summary="Revoke a key immediately")
def revoke_key(key_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.key_read(svc.revoke_key(svc.key(key_id)))


@router.get("/events", response_model=list[EventInfo], summary="Webhook events and example payloads")
def events(ctx: Manage):
    sample_appt = {"id": "8c1f…", "reference": "APT-SUNRISE-01JD8Q…", "status": "confirmed", "start_at": "2026-11-16T05:00:00+00:00", "end_at": "2026-11-16T05:30:00+00:00",
                   "timezone": "Asia/Kolkata", "consultation_mode": "in_person", "source": "online", "meeting_link": None,
                   "service": {"id": "…", "name": "Consultation"}, "professional": {"id": "…", "name": "Dr. Mehta"}, "branch": {"id": "…", "name": "Main"},
                   "customer": {"id": "…", "name": "Asha Patel", "mobile": "+919812345678", "email": "asha@example.com"},
                   "amounts": {"currency": "INR", "total_paise": 50000, "advance_due_paise": 50000, "paid_paise": 50000}}
    sample_pay = {"id": "…", "reference": "PAY-SUNRISE-01JD8R…", "status": "verified", "method": "upi_qr", "kind": "advance", "amount_paise": 50000,
                  "verified_amount_paise": 50000, "utr": "412345678901", "currency": "INR", "verified_at": "2026-11-14T06:12:00+00:00", "rejection_reason": None,
                  "appointment": {"id": "…", "reference": "APT-SUNRISE-01JD8Q…"}}
    sample_refund = {"id": "…", "reference": "RFD-SUNRISE-01JD9…", "status": "processed", "amount_paise": 50000, "method": "upi", "refund_reference": "512345678901",
                     "processed_at": "2026-11-15T10:00:00+00:00", "payment": {"id": "…", "reference": "PAY-SUNRISE-01JD8R…"}}

    def envelope(name, data):
        return {"id": "evt_01JD8S…", "type": name, "api_version": API_VERSION, "created_at": "2026-11-14T06:12:01+00:00",
                "organization": {"id": ctx.organization.public_id, "slug": ctx.organization.slug}, "data": data}

    out = []
    for name, desc in EVENTS.items():
        data = sample_pay if name.startswith("payment.") else sample_refund if name.startswith("refund.") else {"message": "Test event"} if name == "ping" else sample_appt
        if name == "appointment.rescheduled":
            data = {**sample_appt, "previous_start_at": "2026-11-15T09:00:00+00:00"}
        out.append(EventInfo(name=name, description=desc, sample=envelope(name, data)))
    return out


@router.get("/webhooks", response_model=list[WebhookRead])
def list_webhooks(db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return [svc.endpoint_read(e) for e in svc.endpoints()]


@router.post("/webhooks", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED, dependencies=[recent_auth("webhooks")], summary="Add an endpoint (the signing secret is returned once)")
def create_webhook(payload: WebhookCreate, db: DB, ctx: Manage, meta: Meta):
    return _svc(db, ctx, meta).create_endpoint(payload)


@router.patch("/webhooks/{endpoint_id}", response_model=WebhookRead, dependencies=[recent_auth("webhooks")])
def update_webhook(endpoint_id: str, payload: WebhookUpdate, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.endpoint_read(svc.update_endpoint(svc.endpoint(endpoint_id), payload))


@router.delete("/webhooks/{endpoint_id}", response_model=Message)
def delete_webhook(endpoint_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete_endpoint(svc.endpoint(endpoint_id))
    return Message(detail="Webhook endpoint deleted.")


@router.post("/webhooks/{endpoint_id}/rotate-secret", response_model=Message, dependencies=[recent_auth("webhooks")], summary="Replace the signing secret (returned once)")
def rotate_secret(endpoint_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return Message(detail=svc.rotate_secret(svc.endpoint(endpoint_id)))


@router.post("/webhooks/{endpoint_id}/test", response_model=DeliveryDetail, summary="Send a signed ping right now")
def test_webhook(endpoint_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.delivery_read(svc.ping(svc.endpoint(endpoint_id)), detail=True)


@router.get("/webhooks/{endpoint_id}/deliveries", response_model=Page[DeliveryRead])
def deliveries(endpoint_id: str, db: DB, ctx: Manage, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
               status_filter: Annotated[str | None, Query(alias="status")] = None):
    svc = _svc(db, ctx, meta)
    rows, total = svc.deliveries(svc.endpoint(endpoint_id), status=status_filter, page=params.page, page_size=params.page_size)
    return Page(data=[svc.delivery_read(r) for r in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetail)
def delivery(delivery_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.delivery_read(svc.delivery(delivery_id), detail=True)


@router.post("/deliveries/{delivery_id}/redeliver", response_model=DeliveryRead)
def redeliver(delivery_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.delivery_read(svc.redeliver(svc.delivery(delivery_id)))
