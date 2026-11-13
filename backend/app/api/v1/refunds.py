"""Refund requests, approvals and staff-recorded refund completion."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import DB, Meta, TenantContext, get_tenant_context, require_permission
from app.core.exceptions import PermissionDenied
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.schemas.refund import (
    RefundCreate,
    RefundDecision,
    RefundProcess,
    RefundRead,
    RefundReject,
    RefundStats,
    RefundSummary,
)
from app.services.refund_service import RefundService

router = APIRouter(prefix="/refunds", tags=["refunds"])
Approve = Annotated[TenantContext, Depends(require_permission("refunds:approve"))]
Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


def _can_view(ctx: TenantContext) -> None:
    if not (ctx.has("refunds:request") or ctx.has("refunds:approve")):
        raise PermissionDenied("Missing permission: refunds:request", code="permission_denied")


@router.get("", response_model=Page[RefundRead])
def list_refunds(db: DB, ctx: Tenant, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
                 status_filter: Annotated[str | None, Query(alias="status")] = None, search: Annotated[str | None, Query(max_length=64)] = None,
                 from_at: datetime | None = None, to_at: datetime | None = None):
    _can_view(ctx)
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    rows, total = svc.list(status=status_filter, search=search, from_at=from_at, to_at=to_at, page=params.page, page_size=params.page_size)
    return Page(data=[svc.to_read(r) for r in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/stats", response_model=RefundStats)
def refund_stats(db: DB, ctx: Tenant, meta: Meta):
    _can_view(ctx)
    return RefundService(db, ctx.organization, ctx.user, meta).stats()


@router.get("/for-payment/{payment_id}", response_model=RefundSummary, summary="Refundable balance, policy suggestion and refund history of a payment")
def payment_refunds(payment_id: str, db: DB, ctx: Tenant, meta: Meta):
    _can_view(ctx)
    from app.services.payment_service import PaymentService

    return RefundService(db, ctx.organization, ctx.user, meta).summary(PaymentService(db, ctx.organization, ctx.user, meta).get(payment_id))


@router.post("", response_model=RefundRead, status_code=status.HTTP_201_CREATED, summary="Request a refund of a verified payment")
def request_refund(payload: RefundCreate, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("refunds:request"))], meta: Meta):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.request(payload))


@router.get("/{refund_id}", response_model=RefundRead)
def get_refund(refund_id: str, db: DB, ctx: Tenant, meta: Meta):
    _can_view(ctx)
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.get(refund_id))


@router.post("/{refund_id}/approve", response_model=RefundRead)
def approve_refund(refund_id: str, payload: RefundDecision, db: DB, ctx: Approve, meta: Meta):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.approve(svc.get(refund_id), payload.notes))


@router.post("/{refund_id}/reject", response_model=RefundRead)
def reject_refund(refund_id: str, payload: RefundReject, db: DB, ctx: Approve, meta: Meta):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.reject(svc.get(refund_id), payload))


@router.post("/{refund_id}/cancel", response_model=RefundRead, summary="Withdraw a refund request")
def cancel_refund(refund_id: str, payload: RefundDecision, db: DB, ctx: Tenant, meta: Meta):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    refund = svc.get(refund_id)
    if not (ctx.has("refunds:approve") or (ctx.has("refunds:request") and refund.requested_by_user_id == ctx.user.id)):
        raise PermissionDenied("Only the requester or an approver can withdraw this refund.", code="permission_denied")
    return svc.to_read(svc.cancel(refund, payload.notes))


@router.post("/{refund_id}/process", response_model=RefundRead, summary="Record a refund that staff already sent from the organization's own bank/UPI app")
def process_refund(refund_id: str, payload: RefundProcess, db: DB, ctx: Approve, meta: Meta):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.process(svc.get(refund_id), payload))


@router.post("/{refund_id}/proof", response_model=RefundRead, summary="Attach the refund screenshot/receipt (private)")
async def upload_proof(refund_id: str, db: DB, ctx: Approve, meta: Meta, file: UploadFile = File(...)):
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    data = await file.read()
    return svc.to_read(svc.attach_proof(svc.get(refund_id), data))


@router.get("/{refund_id}/proof", summary="Refund proof (private; access is audit-logged)")
def get_proof(refund_id: str, db: DB, ctx: Tenant, meta: Meta):
    _can_view(ctx)
    svc = RefundService(db, ctx.organization, ctx.user, meta)
    mime, handle = svc.open_proof(svc.get(refund_id))
    return StreamingResponse(handle, media_type=mime, headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})
