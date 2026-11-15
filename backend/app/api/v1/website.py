"""Website Management: edit the draft, publish, history and restore (permissions website:write / website:publish)."""
from __future__ import annotations

from datetime import date as _date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.schemas.website import DraftUpdate, PublishRequest, WebsiteState, WebsiteVersionRead
from app.services.website_service import WebsiteService

router = APIRouter(prefix="/website", tags=["website"])

Editor = Annotated[TenantContext, Depends(require_permission("website:write"))]
Publisher = Annotated[TenantContext, Depends(require_permission("website:publish"))]


def _svc(db, ctx: TenantContext, meta) -> WebsiteService:
    return WebsiteService(db, ctx.organization, ctx.user, meta)


@router.get("", response_model=WebsiteState, summary="Draft and published website with editing state")
def get_website(db: DB, ctx: Editor, meta: Meta):
    return _svc(db, ctx, meta).state()


@router.put("/draft", response_model=WebsiteState, summary="Save the draft (send the lock_version you loaded)")
def save_draft(body: DraftUpdate, db: DB, ctx: Editor, meta: Meta):
    return _svc(db, ctx, meta).save_draft(body.document, body.lock_version)


@router.post("/publish", response_model=WebsiteState, summary="Publish the current draft")
def publish(body: PublishRequest, db: DB, ctx: Publisher, meta: Meta):
    return _svc(db, ctx, meta).publish(body.lock_version, body.note)


@router.post("/draft/discard", response_model=WebsiteState, summary="Replace the draft with the published website")
def discard(body: PublishRequest, db: DB, ctx: Editor, meta: Meta):
    return _svc(db, ctx, meta).discard_draft(body.lock_version)


@router.get("/versions", response_model=list[WebsiteVersionRead], summary="Published versions, newest first")
def versions(db: DB, ctx: Editor, meta: Meta):
    return _svc(db, ctx, meta).versions()


@router.post("/versions/{version}/restore", response_model=WebsiteState, summary="Copy a published version into the draft")
def restore(version: int, body: PublishRequest, db: DB, ctx: Publisher, meta: Meta):
    return _svc(db, ctx, meta).restore(version, body.lock_version)


Analyst = Annotated[TenantContext, Depends(require_permission("reports:read"))]


@router.get("/analytics", summary="Website traffic and booking funnel for a date range (cookie-free counts)")
def analytics(db: DB, ctx: Analyst, from_date: _date | None = None, to_date: _date | None = None):
    from datetime import timedelta

    from app.core.exceptions import ValidationFailed
    from app.services.website_analytics_service import WebsiteAnalyticsService

    service = WebsiteAnalyticsService(db, ctx.organization)
    end = to_date or service.today()  # the clinic's own date, not the server's (they differ for hours every night)
    start = from_date or end - timedelta(days=29)
    if start > end or (end - start).days > 366:
        raise ValidationFailed("Choose a range of up to one year.", code="invalid_range")
    return service.report(start, end)
