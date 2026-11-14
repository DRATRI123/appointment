"""UPI accounts, payments, the verification queue and coupons (tenant routes)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import DB, Meta, TenantContext, get_tenant_context, require_permission
from app.core.exceptions import PermissionDenied
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.schemas.common import APIModel, Message
from app.schemas.payment import (
    Checkout,
    CouponCreate,
    CouponRead,
    CouponUpdate,
    NoteRequest,
    PaymentCreate,
    PaymentDetail,
    PaymentRead,
    PaymentStats,
    QRPreview,
    RejectRequest,
    UPIAccountCreate,
    UPIAccountRead,
    UPIAccountUpdate,
    VerifyRequest,
)
from app.services.coupon_service import CouponService
from app.services.payment_service import PaymentService
from app.services.upi_account_service import UPIAccountService

ReadUPI = Annotated[TenantContext, Depends(require_permission("upi_accounts:read"))]
WriteUPI = Annotated[TenantContext, Depends(require_permission("upi_accounts:write"))]
ReadPay = Annotated[TenantContext, Depends(require_permission("payments:read"))]
VerifyPay = Annotated[TenantContext, Depends(require_permission("payments:verify"))]
ReadSvc = Annotated[TenantContext, Depends(require_permission("services:read"))]
WriteSvc = Annotated[TenantContext, Depends(require_permission("services:write"))]

# ---------------------------------------------------------------- UPI accounts
upi_router = APIRouter(prefix="/upi-accounts", tags=["upi-accounts"])


class AssignAccount(APIModel):
    service_id: str
    upi_account_id: str | None = None


@upi_router.get("", response_model=list[UPIAccountRead])
def list_accounts(db: DB, ctx: ReadUPI, meta: Meta, include_inactive: bool = True):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    return [svc.to_read(a) for a in svc.list(include_inactive)]


@upi_router.post("", response_model=UPIAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: UPIAccountCreate, db: DB, ctx: WriteUPI, meta: Meta):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.create(payload))


@upi_router.post("/assign", response_model=Message, summary="Collect a service's payments into a specific account (null resets to branch/organization default)")
def assign_account(payload: AssignAccount, db: DB, ctx: WriteUPI, meta: Meta):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    acct = svc.get(payload.upi_account_id) if payload.upi_account_id else None
    service = svc.assign_service(acct, payload.service_id)
    return Message(detail=f"{service.name} now collects into {acct.display_name if acct else 'the default account'}.")


@upi_router.get("/{account_id}", response_model=UPIAccountRead)
def get_account(account_id: str, db: DB, ctx: ReadUPI, meta: Meta):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.get(account_id))


@upi_router.patch("/{account_id}", response_model=UPIAccountRead)
def update_account(account_id: str, payload: UPIAccountUpdate, db: DB, ctx: WriteUPI, meta: Meta):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.update(svc.get(account_id), payload))


@upi_router.delete("/{account_id}", response_model=Message)
def delete_account(account_id: str, db: DB, ctx: WriteUPI, meta: Meta):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    svc.delete(svc.get(account_id))
    return Message(detail="UPI account removed.")


@upi_router.get("/{account_id}/preview", response_model=QRPreview, summary="Preview the QR a customer would scan (test amount)")
def preview_account(account_id: str, db: DB, ctx: ReadUPI, meta: Meta, amount_paise: Annotated[int | None, Query(ge=1, le=10_000_000)] = 100):
    svc = UPIAccountService(db, ctx.organization, ctx.user, meta)
    return svc.preview(svc.get(account_id), amount_paise)


# -------------------------------------------------------------------- payments
payments_router = APIRouter(prefix="/payments", tags=["payments"])


@payments_router.get("", response_model=Page[PaymentRead])
def list_payments(
    db: DB, ctx: ReadPay, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[str | None, Query(alias="status")] = None, method: str | None = None,
    from_at: datetime | None = None, to_at: datetime | None = None, search: Annotated[str | None, Query(max_length=64)] = None,
    appointment_id: str | None = None, customer_id: str | None = None,
):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    rows, total = svc.list(status=status_filter, method=method, from_at=from_at, to_at=to_at, search=search, appointment_id=appointment_id,
                           customer_id=customer_id, page=params.page, page_size=params.page_size)
    return Page(data=[svc.to_read(p) for p in svc.prepare_reads(rows)], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@payments_router.post("", response_model=PaymentDetail, status_code=status.HTTP_201_CREATED,
                      summary="Request a UPI payment, record cash, or log a bank transfer for an appointment (amount computed by the server)")
def create_payment(payload: PaymentCreate, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(get_tenant_context)]):
    ctx.require("payments:record" if payload.method == "cash" else "payments:read")
    if payload.method != "cash" and not (ctx.has("payments:record") or ctx.has("appointments:write")):
        raise PermissionDenied("Missing permission: payments:record", code="permission_denied")
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.to_detail(svc.staff_create(payload))


@payments_router.get("/{payment_id}", response_model=PaymentDetail)
def get_payment(payment_id: str, db: DB, ctx: ReadPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.to_detail(svc.get(payment_id))


@payments_router.get("/{payment_id}/checkout", response_model=Checkout, summary="QR and UPI details to show at the reception desk")
def staff_checkout(payment_id: str, db: DB, ctx: ReadPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.checkout(svc.get(payment_id))


@payments_router.get("/{payment_id}/submissions/{submission_id}/screenshot", summary="Payment screenshot (private; access is audit-logged)")
def screenshot(payment_id: str, submission_id: str, db: DB, ctx: ReadPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    sub, handle = svc.open_screenshot(svc.get(payment_id), submission_id)
    return StreamingResponse(handle, media_type=sub.screenshot_mime or "application/octet-stream", headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})


# ------------------------------------------------------------ verification queue
admin_router = APIRouter(prefix="/admin/payments", tags=["payment-verification"])


@admin_router.get("/stats", response_model=PaymentStats)
def stats(db: DB, ctx: ReadPay, meta: Meta):
    return PaymentService(db, ctx.organization, ctx.user, meta).stats()


@admin_router.get("/queue", response_model=Page[PaymentRead], summary="Payments waiting for verification, oldest submission first")
def queue(db: DB, ctx: VerifyPay, meta: Meta, params: Annotated[PageParams, Depends(page_params)], status_filter: Annotated[str, Query(alias="status")] = "submitted,under_review"):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    rows, total = svc.list(status=status_filter, method=None, from_at=None, to_at=None, search=None, appointment_id=None, customer_id=None, page=params.page, page_size=params.page_size)
    return Page(data=[svc.to_read(p) for p in svc.prepare_reads(rows)], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@admin_router.post("/{payment_id}/review", response_model=PaymentDetail)
def start_review(payment_id: str, db: DB, ctx: VerifyPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.to_detail(svc.start_review(svc.get(payment_id)))


@admin_router.post("/{payment_id}/verify", response_model=PaymentDetail, summary="Approve after confirming the bank credit")
def verify(payment_id: str, payload: VerifyRequest, db: DB, ctx: VerifyPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.to_detail(svc.verify(svc.get(payment_id), payload))


@admin_router.post("/{payment_id}/reject", response_model=PaymentDetail)
def reject(payment_id: str, payload: RejectRequest, db: DB, ctx: VerifyPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    return svc.to_detail(svc.reject(svc.get(payment_id), payload))


@admin_router.post("/{payment_id}/notes", response_model=PaymentDetail)
def add_note(payment_id: str, payload: NoteRequest, db: DB, ctx: VerifyPay, meta: Meta):
    svc = PaymentService(db, ctx.organization, ctx.user, meta)
    p = svc.get(payment_id)
    svc.add_note(p, payload.notes)
    return svc.to_detail(p)


# --------------------------------------------------------------------- coupons
coupons_router = APIRouter(prefix="/coupons", tags=["coupons"])


@coupons_router.get("", response_model=list[CouponRead])
def list_coupons(db: DB, ctx: ReadSvc, meta: Meta):
    svc = CouponService(db, ctx.organization, ctx.user, meta)
    return [svc.to_read(c) for c in svc.list()]


@coupons_router.post("", response_model=CouponRead, status_code=status.HTTP_201_CREATED)
def create_coupon(payload: CouponCreate, db: DB, ctx: WriteSvc, meta: Meta):
    svc = CouponService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.create(payload))


@coupons_router.patch("/{coupon_id}", response_model=CouponRead)
def update_coupon(coupon_id: str, payload: CouponUpdate, db: DB, ctx: WriteSvc, meta: Meta):
    svc = CouponService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.update(svc.get(coupon_id), payload))


@coupons_router.delete("/{coupon_id}", response_model=Message)
def delete_coupon(coupon_id: str, db: DB, ctx: WriteSvc, meta: Meta):
    svc = CouponService(db, ctx.organization, ctx.user, meta)
    svc.delete(svc.get(coupon_id))
    return Message(detail="Coupon deleted.")
