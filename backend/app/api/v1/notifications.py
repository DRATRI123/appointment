"""Notification outbox, templates, provider status, the personal inbox and customer preferences."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Meta, TenantContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.models import Customer, Organization
from app.schemas.common import APIModel, Message
from app.schemas.notification import (
    EventInfo,
    Inbox,
    NotificationDetail,
    NotificationRead,
    NotificationSettings,
    NotificationStats,
    Preferences,
    PreferencesUpdate,
    PreviewRequest,
    PreviewResponse,
    ProviderStatus,
    TemplateRead,
    TemplateUpsert,
    TestSendRequest,
)
from app.services.audit_service import record_audit
from app.services.notification_service import NotificationService, inbox_for, mark_read, preferences_of

router = APIRouter(prefix="/notifications", tags=["notifications"])
me_router = APIRouter(tags=["notifications"])
Read = Annotated[TenantContext, Depends(require_permission("notifications:read"))]
Write = Annotated[TenantContext, Depends(require_permission("notifications:write"))]


def _svc(db, ctx: TenantContext, meta) -> NotificationService:
    return NotificationService(db, ctx.organization, ctx.user, meta)


@router.get("", response_model=Page[NotificationRead], summary="Outbox: every message created for this organization")
def list_notifications(db: DB, ctx: Read, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
                       status_filter: Annotated[str | None, Query(alias="status")] = None, channel: Annotated[str | None, Query(pattern=r"^(email|sms|whatsapp|in_app)$")] = None,
                       event: str | None = None, search: Annotated[str | None, Query(max_length=64)] = None):
    svc = _svc(db, ctx, meta)
    rows, total = svc.list(status=status_filter, channel=channel, event=event, search=search, page=params.page, page_size=params.page_size)
    from app.core.preload import preload
    from app.models import Appointment

    preload(db, Appointment, (n.appointment_id for n in rows))  # one query for the page, not one per message
    return Page(data=[svc.to_read(n) for n in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/stats", response_model=NotificationStats)
def stats(db: DB, ctx: Read, meta: Meta):
    return _svc(db, ctx, meta).stats()


@router.get("/providers", response_model=list[ProviderStatus], summary="Which delivery adapter each channel uses (no secrets)")
def providers(db: DB, ctx: Read, meta: Meta):
    return _svc(db, ctx, meta).providers()


@router.get("/settings", response_model=NotificationSettings)
def get_settings_(db: DB, ctx: Read, meta: Meta):
    cfg = _svc(db, ctx, meta).settings()
    return NotificationSettings.model_validate({k: v for k, v in cfg.items() if k in NotificationSettings.model_fields})


@router.put("/settings", response_model=NotificationSettings, summary="Channels, reminder times and per-event channel choices")
def put_settings(payload: NotificationSettings, db: DB, ctx: Write, meta: Meta):
    from app.services.organization_service import OrganizationService

    values = payload.model_dump()
    values["events"] = {k: v for k, v in values["events"].items()}
    OrganizationService(db, meta).update_settings(ctx.organization, "notification", values, ctx.user)
    return get_settings_(db, ctx, meta)


@router.get("/events", response_model=list[EventInfo])
def events(db: DB, ctx: Read, meta: Meta):
    return _svc(db, ctx, meta).events()


@router.get("/templates", response_model=list[TemplateRead])
def templates(db: DB, ctx: Read, meta: Meta):
    return _svc(db, ctx, meta).templates()


@router.put("/templates/{event}/{channel}", response_model=TemplateRead, summary="Customise a template for this organization")
def save_template(event: str, channel: str, payload: TemplateUpsert, db: DB, ctx: Write, meta: Meta):
    return _svc(db, ctx, meta).upsert_template(event, channel, payload)


@router.delete("/templates/{event}/{channel}", response_model=TemplateRead, summary="Go back to the platform default")
def reset_template(event: str, channel: str, db: DB, ctx: Write, meta: Meta):
    return _svc(db, ctx, meta).reset_template(event, channel)


@router.post("/templates/{event}/{channel}/preview", response_model=PreviewResponse, summary="Render with sample data")
def preview(event: str, channel: str, payload: PreviewRequest, db: DB, ctx: Read, meta: Meta):
    return _svc(db, ctx, meta).preview(event, channel, payload.subject, payload.body)


@router.post("/test", response_model=NotificationDetail, summary="Send a test message through the configured provider")
def send_test(payload: TestSendRequest, db: DB, ctx: Write, meta: Meta):
    return _svc(db, ctx, meta).send_test(payload.channel, payload.to)


@router.get("/{notification_id}", response_model=NotificationDetail)
def get_notification(notification_id: str, db: DB, ctx: Read, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_detail(svc.get(notification_id))


@router.post("/{notification_id}/retry", response_model=NotificationDetail)
def retry(notification_id: str, db: DB, ctx: Write, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_detail(svc.retry(svc.get(notification_id)))


@router.post("/{notification_id}/cancel", response_model=NotificationDetail)
def cancel(notification_id: str, db: DB, ctx: Write, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_detail(svc.cancel(svc.get(notification_id)))


# ------------------------------------------------------------------ personal inbox
class MarkRead(APIModel):
    ids: list[str] | None = None


@me_router.get("/me/notifications", response_model=Inbox, summary="In-app notifications of the signed-in user (all organizations)")
def my_inbox(db: DB, user: CurrentUser, unread_only: bool = False, limit: Annotated[int, Query(ge=1, le=100)] = 30):
    return inbox_for(db, user, unread_only=unread_only, limit=limit)


@me_router.post("/me/notifications/read", response_model=Message, summary="Mark some (ids) or all in-app notifications as read")
def my_inbox_read(payload: MarkRead, db: DB, user: CurrentUser):
    n = mark_read(db, user, payload.ids)
    return Message(detail=f"{n} marked as read.")


# ------------------------------------------------------------------ customer preferences
class OrgPreferences(Preferences):
    organization_id: str
    organization_name: str
    whatsapp_available: bool


def _customers(db, user) -> list[Customer]:
    from app.services.customer_link import owned_customer_ids

    return list(db.scalars(select(Customer).where(Customer.id.in_(owned_customer_ids(db, user)))).all())


@me_router.get("/customer/notification-preferences", response_model=list[OrgPreferences], summary="Message preferences per clinic")
def my_preferences(db: DB, user: CurrentUser):
    out = []
    for c in _customers(db, user):
        org = db.get(Organization, c.organization_id)
        cfg = NotificationService(db, org).settings()
        out.append(OrgPreferences(**preferences_of(c).model_dump(), organization_id=org.public_id, organization_name=org.name, whatsapp_available=bool(cfg.get("whatsapp_enabled"))))
    return out


@me_router.patch("/customer/notification-preferences/{organization_id}", response_model=OrgPreferences)
def update_preferences(organization_id: str, payload: PreferencesUpdate, db: DB, user: CurrentUser, meta: Meta):
    from app.core.time import utcnow

    for c in _customers(db, user):
        org = db.get(Organization, c.organization_id)
        if org.public_id != organization_id:
            continue
        prefs = dict(c.communication_preferences or {})
        before = preferences_of(c).model_dump()
        for key, value in payload.model_dump(exclude_none=True).items():
            prefs[key] = value
            if key == "whatsapp":
                prefs["whatsapp_opt_in_at" if value else "whatsapp_opt_out_at"] = utcnow().isoformat()
                prefs["whatsapp_opt_in_source"] = "customer"
        c.communication_preferences = prefs
        record_audit(db, action="customer.notification_preferences_updated", actor=user, organization_id=org.id, entity_type="customer", entity_id=c.public_id,
                     before=before, after=preferences_of(c).model_dump(), meta=meta)
        cfg = NotificationService(db, org).settings()
        return OrgPreferences(**preferences_of(c).model_dump(), organization_id=org.public_id, organization_name=org.name, whatsapp_available=bool(cfg.get("whatsapp_enabled")))
    raise NotFoundError("You have no customer profile with this organization.")

