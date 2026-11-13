"""Appointments, holds, recurring bookings, waitlist (staff) and the customer's own appointments."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser, Meta, TenantContext, get_tenant_context, require_permission
from app.core.exceptions import PermissionDenied
from app.models import Appointment, Branch, Customer, Organization, Professional, Service, User, Waitlist
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentRead,
    CalendarEvent,
    CustomerSummary,
    HoldCreate,
    HoldRead,
    RecurringCreate,
    RecurringResult,
    RescheduleRequest,
    StatusAction,
    StatusHistoryRead,
    WaitlistCreate,
    WaitlistRead,
)
from app.schemas.common import Message
from app.services.appointment_service import AppointmentService
from app.services.catalog_service import ids_to_public

router = APIRouter(tags=["appointments"])
ReadAppts = Annotated[TenantContext, Depends(require_permission("appointments:read"))]
WriteAppts = Annotated[TenantContext, Depends(require_permission("appointments:write"))]
CheckinAppts = Annotated[TenantContext, Depends(require_permission("appointments:checkin"))]


# ------------------------------------------------------------- serializers
def hold_read(db: Session, hold) -> HoldRead:
    pro = ids_to_public(db, Professional, {hold.professional_id})[hold.professional_id]
    branch = ids_to_public(db, Branch, {hold.branch_id})[hold.branch_id]
    service = ids_to_public(db, Service, {hold.service_id})[hold.service_id]
    return HoldRead(id=hold.public_id, professional_id=pro, branch_id=branch, service_id=service, start_at=hold.start_at, end_at=hold.end_at,
                    expires_at=hold.expires_at, session_key=hold.session_key, status=hold.status)


def appointment_read(db: Session, appt: Appointment, *, include_internal: bool = False, include_token: bool = False, service: AppointmentService | None = None, viewer_is_customer: bool = False) -> AppointmentRead:
    org = db.get(Organization, appt.organization_id)
    branch = db.get(Branch, appt.branch_id)
    pro = db.get(Professional, appt.professional_id)
    svc = db.get(Service, appt.service_id)
    cust = db.get(Customer, appt.customer_id)
    service = service or AppointmentService(db, org)
    from app.models import CustomerDependent

    dep = ids_to_public(db, CustomerDependent, {appt.dependent_id}).get(appt.dependent_id) if appt.dependent_id else None
    parent = ids_to_public(db, Appointment, {appt.parent_appointment_id}).get(appt.parent_appointment_id) if appt.parent_appointment_id else None
    return AppointmentRead(
        id=appt.public_id, reference=appt.reference, status=appt.status, source=appt.source, organization_id=org.public_id, organization_name=org.name,
        organization_slug=org.slug, branch_id=branch.public_id, branch_name=branch.name, professional_id=pro.public_id, professional_name=pro.display_name,
        service_id=svc.public_id, service_name=svc.name,
        customer=CustomerSummary(id=cust.public_id, full_name=cust.full_name, mobile=cust.mobile, email=cust.email, is_guest=cust.is_guest),
        dependent_id=dep, start_at=appt.start_at, end_at=appt.end_at, timezone=appt.timezone, consultation_mode=appt.consultation_mode, currency=appt.currency,
        subtotal_paise=appt.subtotal_paise, discount_paise=appt.discount_paise, tax_paise=appt.tax_paise, total_amount_paise=appt.total_amount_paise,
        advance_due_paise=appt.advance_due_paise, paid_amount_paise=appt.paid_amount_paise, payment_due_at=appt.payment_due_at, customer_notes=appt.customer_notes,
        internal_notes=appt.internal_notes if include_internal else None, meeting_link=appt.meeting_link, is_follow_up=appt.is_follow_up,
        recurrence_group_id=appt.recurrence_group_id, parent_appointment_id=parent, confirmed_at=appt.confirmed_at, checked_in_at=appt.checked_in_at,
        completed_at=appt.completed_at, cancelled_at=appt.cancelled_at, created_at=appt.created_at,
        can_cancel=service.customer_can(appt, "cancel") if viewer_is_customer else appt.status in ("pending_payment", "pending_verification", "confirmed", "checked_in"),
        can_reschedule=service.customer_can(appt, "reschedule") if viewer_is_customer else appt.status in ("pending_payment", "pending_verification", "confirmed"),
        access_token=(appt.metadata_ or {}).get("access_token") if include_token else None,
    )


def appointment_detail(db: Session, appt: Appointment, **kwargs) -> AppointmentDetail:
    base = appointment_read(db, appt, **kwargs)
    users = ids_to_public(db, User, {h.changed_by_user_id for h in appt.status_history if h.changed_by_user_id})
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(list(users)))).all()) if users else {}
    history = [StatusHistoryRead(from_status=h.from_status, to_status=h.to_status, changed_at=h.changed_at, reason=h.reason, changed_by=names.get(h.changed_by_user_id)) for h in appt.status_history]
    from app.services.form_service import FormService

    response = FormService(db, db.get(Organization, appt.organization_id)).response_for_appointment(appt)
    return AppointmentDetail(**base.model_dump(), history=history, pricing_snapshot=appt.pricing_snapshot if kwargs.get("include_internal") else None,
                             form_answers=response.answers if response else None)


def waitlist_read(db: Session, row: Waitlist) -> WaitlistRead:
    cust = db.get(Customer, row.customer_id)
    return WaitlistRead(
        id=row.public_id, customer=CustomerSummary(id=cust.public_id, full_name=cust.full_name, mobile=cust.mobile, email=cust.email, is_guest=cust.is_guest),
        branch_id=ids_to_public(db, Branch, {row.branch_id}).get(row.branch_id) if row.branch_id else None,
        professional_id=ids_to_public(db, Professional, {row.professional_id}).get(row.professional_id) if row.professional_id else None,
        service_id=ids_to_public(db, Service, {row.service_id}).get(row.service_id) if row.service_id else None,
        preferred_date=row.preferred_date, status=row.status, notes=row.notes, created_at=row.created_at,
    )


def _own_professional_id(db: Session, ctx: TenantContext) -> int | None:
    """Doctors/professionals with only appointments:read_own see their own calendar."""
    if ctx.has("appointments:read"):
        return None
    if not ctx.has("appointments:read_own"):
        raise PermissionDenied("Missing permission: appointments:read", code="permission_denied")
    pro = db.scalar(select(Professional).where(Professional.organization_id == ctx.organization.id, Professional.user_id == ctx.user.id, Professional.deleted_at.is_(None)))
    if pro is None:
        raise PermissionDenied("No professional profile is linked to your account.", code="no_professional_profile")
    return pro.id


# ------------------------------------------------------------------ holds
@router.post("/appointments/holds", response_model=HoldRead, status_code=status.HTTP_201_CREATED, summary="Reserve a slot for a few minutes (staff)")
def create_hold(payload: HoldCreate, db: DB, ctx: WriteAppts, meta: Meta):
    return hold_read(db, AppointmentService(db, ctx.organization, ctx.user, meta).create_hold(payload, ignore_notice=True))


@router.delete("/appointments/holds/{hold_id}", response_model=Message)
def release_hold(hold_id: str, db: DB, ctx: WriteAppts, meta: Meta):
    AppointmentService(db, ctx.organization, ctx.user, meta).release_hold(hold_id)
    return Message(detail="Hold released.")


# ------------------------------------------------------------ appointments
@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    from_at: datetime | None = None, to_at: datetime | None = None, professional_id: str | None = None, branch_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None, customer_id: str | None = None, search: Annotated[str | None, Query(max_length=100)] = None,
):
    own = _own_professional_id(db, ctx)
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    rows = service.list(from_at=from_at, to_at=to_at, professional_id=professional_id, branch_id=branch_id, status=status_filter, customer_id=customer_id, search=search, restrict_professional_id=own)
    return [appointment_read(db, a, include_internal=True, service=service) for a in rows]


@router.get("/appointments/calendar", response_model=list[CalendarEvent])
def calendar(db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(get_tenant_context)], from_at: datetime, to_at: datetime, professional_id: str | None = None, branch_id: str | None = None):
    own = _own_professional_id(db, ctx)
    rows = AppointmentService(db, ctx.organization, ctx.user, meta).list(from_at=from_at, to_at=to_at, professional_id=professional_id, branch_id=branch_id, status=None, customer_id=None, search=None, restrict_professional_id=own)
    pros = dict(db.execute(select(Professional.id, Professional.display_name).where(Professional.organization_id == ctx.organization.id)).all())
    pro_pub = ids_to_public(db, Professional, {a.professional_id for a in rows})
    branch_pub = ids_to_public(db, Branch, {a.branch_id for a in rows})
    svcs = dict(db.execute(select(Service.id, Service.name).where(Service.organization_id == ctx.organization.id)).all())
    custs = dict(db.execute(select(Customer.id, Customer.full_name).where(Customer.organization_id == ctx.organization.id)).all())
    return [
        CalendarEvent(id=a.public_id, title=f"{custs.get(a.customer_id, '')} · {svcs.get(a.service_id, '')}", start=a.start_at, end=a.end_at, status=a.status,
                      professional_id=pro_pub[a.professional_id], professional_name=pros.get(a.professional_id, ""), branch_id=branch_pub[a.branch_id],
                      service_name=svcs.get(a.service_id, ""), customer_name=custs.get(a.customer_id, ""), reference=a.reference)
        for a in rows
    ]


@router.post("/appointments", response_model=AppointmentDetail, status_code=status.HTTP_201_CREATED, summary="Book for a customer (reception, walk-in, professional)")
def create_appointment(payload: AppointmentCreate, db: DB, ctx: WriteAppts, meta: Meta):
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    appt = service.create(payload, user=ctx.user, staff=True)
    return appointment_detail(db, service.get(appt.public_id), include_internal=True, service=service)


@router.post("/appointments/recurring", response_model=RecurringResult, status_code=status.HTTP_201_CREATED)
def create_recurring(payload: RecurringCreate, db: DB, ctx: WriteAppts, meta: Meta):
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    group, created, skipped = service.create_recurring(payload, user=ctx.user, staff=True)
    return RecurringResult(recurrence_group_id=group, created=[appointment_read(db, a, include_internal=True, service=service) for a in created], skipped=skipped)


@router.get("/appointments/{appointment_id}", response_model=AppointmentDetail)
def get_appointment(appointment_id: str, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(get_tenant_context)]):
    own = _own_professional_id(db, ctx)
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    appt = service.get(appointment_id)
    if own is not None and appt.professional_id != own:
        raise PermissionDenied("Not your appointment.", code="permission_denied")
    return appointment_detail(db, appt, include_internal=True, service=service)


@router.post("/appointments/{appointment_id}/status", response_model=AppointmentDetail, summary="confirm | check_in | start | complete | no_show | cancel | expire")
def change_status(appointment_id: str, payload: StatusAction, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(get_tenant_context)]):
    needed = "appointments:write" if payload.action in ("confirm", "cancel", "expire") else "appointments:checkin"
    ctx.require(needed)
    own = _own_professional_id(db, ctx) if not ctx.has("appointments:read") else None
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    appt = service.get(appointment_id)
    if own is not None and appt.professional_id != own:
        raise PermissionDenied("Not your appointment.", code="permission_denied")
    service.transition(appt, payload.action, reason=payload.reason)
    return appointment_detail(db, service.get(appt.public_id), include_internal=True, service=service)


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentDetail)
def reschedule(appointment_id: str, payload: RescheduleRequest, db: DB, ctx: WriteAppts, meta: Meta):
    service = AppointmentService(db, ctx.organization, ctx.user, meta)
    appt = service.reschedule(service.get(appointment_id), payload)
    return appointment_detail(db, service.get(appt.public_id), include_internal=True, service=service)


# --------------------------------------------------------------- waitlist
@router.get("/waitlist", response_model=list[WaitlistRead])
def list_waitlist(db: DB, ctx: ReadAppts, meta: Meta):
    return [waitlist_read(db, w) for w in AppointmentService(db, ctx.organization, ctx.user, meta).list_waitlist()]


@router.post("/waitlist", response_model=WaitlistRead, status_code=status.HTTP_201_CREATED)
def add_waitlist(payload: WaitlistCreate, db: DB, ctx: WriteAppts, meta: Meta):
    return waitlist_read(db, AppointmentService(db, ctx.organization, ctx.user, meta).add_to_waitlist(payload, user=ctx.user, staff=True))


@router.delete("/waitlist/{entry_id}", response_model=Message)
def remove_waitlist(entry_id: str, db: DB, ctx: WriteAppts, meta: Meta):
    AppointmentService(db, ctx.organization, ctx.user, meta).remove_from_waitlist(entry_id)
    return Message(detail="Removed from waitlist.")


# ------------------------------------------------------ customer's own view
customer_router = APIRouter(prefix="/customer", tags=["customer"])


@customer_router.get("/appointments", response_model=list[AppointmentRead], summary="All appointments of the signed-in customer across organizations")
def my_appointments(db: DB, user: CurrentUser):
    rows = db.scalars(
        select(Appointment).join(Customer, Customer.id == Appointment.customer_id).where(Customer.user_id == user.id).order_by(Appointment.start_at.desc())
    ).all()
    out = []
    for a in rows:
        org = db.get(Organization, a.organization_id)
        out.append(appointment_read(db, a, service=AppointmentService(db, org), viewer_is_customer=True))
    return out


def _own_appointment(db: Session, user: User, appointment_id: str) -> tuple[Appointment, AppointmentService]:
    appt = db.scalar(select(Appointment).join(Customer, Customer.id == Appointment.customer_id).where(Appointment.public_id == appointment_id, Customer.user_id == user.id))
    if appt is None:
        raise PermissionDenied("Appointment not found.", code="not_found")
    org = db.get(Organization, appt.organization_id)
    return appt, AppointmentService(db, org, user)


@customer_router.get("/appointments/{appointment_id}", response_model=AppointmentDetail)
def my_appointment(appointment_id: str, db: DB, user: CurrentUser):
    appt, service = _own_appointment(db, user, appointment_id)
    return appointment_detail(db, service.get(appt.public_id), service=service, viewer_is_customer=True)


@customer_router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentDetail)
def cancel_mine(appointment_id: str, payload: StatusAction, db: DB, user: CurrentUser):
    appt, service = _own_appointment(db, user, appointment_id)
    service.transition(appt, "cancel", reason=payload.reason, by_customer=True)
    return appointment_detail(db, service.get(appt.public_id), service=service, viewer_is_customer=True)


@customer_router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentDetail)
def reschedule_mine(appointment_id: str, payload: RescheduleRequest, db: DB, user: CurrentUser):
    appt, service = _own_appointment(db, user, appointment_id)
    service.reschedule(appt, payload, by_customer=True, session_key=None)
    return appointment_detail(db, service.get(appt.public_id), service=service, viewer_is_customer=True)



@customer_router.get("/payments", summary="Payments of the signed-in customer across organizations")
def my_payments(db: DB, user: CurrentUser) -> list[dict]:
    from app.models import Payment
    from app.services.payment_service import PaymentService

    rows = db.scalars(select(Payment).join(Customer, Customer.id == Payment.customer_id).where(Customer.user_id == user.id).order_by(Payment.created_at.desc())).all()
    out = []
    for p in rows:
        org = db.get(Organization, p.organization_id)
        read = PaymentService(db, org).to_read(p).model_dump(mode="json")
        read["organization_name"], read["organization_slug"] = org.name, org.slug
        out.append(read)
    return out
