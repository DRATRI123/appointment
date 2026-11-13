"""Unauthenticated catalogue for the public booking website. Only active, bookable data is exposed."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DB
from app.core.exceptions import NotFoundError
from app.models import Organization, ServiceCategory
from app.schemas.catalog import BranchRead, CategoryRead, ProfessionalRead, ServiceRead
from app.schemas.common import APIModel
from app.schemas.organization import OrganizationRead
from app.services.catalog_service import CatalogService, ids_to_public
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/public", tags=["public"])


class PublicOrganization(APIModel):
    organization: OrganizationRead
    branches: list[BranchRead]
    categories: list[CategoryRead]
    settings: dict


def _org(db: Session, slug: str) -> tuple[Organization, CatalogService]:
    org = OrganizationService(db).get_by_slug_public(slug)
    return org, CatalogService(db, org)


def _public_settings(db: Session, org: Organization) -> dict:
    all_settings = OrganizationService(db).get_settings(org)
    return {ns: all_settings.get(ns, {}) for ns in ("branding", "booking", "cancellation", "legal", "general")}


@router.get("/organizations/{slug}", response_model=PublicOrganization)
def organization(slug: str, db: DB) -> PublicOrganization:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import category_read

    rows = catalog.list_categories(include_inactive=False)
    parents = ids_to_public(db, ServiceCategory, {c.parent_id for c, _ in rows if c.parent_id})
    return PublicOrganization(
        organization=OrganizationRead.model_validate(org),
        branches=[BranchRead.model_validate(b) for b in catalog.list_branches(include_inactive=False)],
        categories=[category_read(c, n, parents) for c, n in rows],
        settings=_public_settings(db, org),
    )


@router.get("/organizations/{slug}/branches", response_model=list[BranchRead])
def branches(slug: str, db: DB) -> list[BranchRead]:
    _, catalog = _org(db, slug)
    return [BranchRead.model_validate(b) for b in catalog.list_branches(include_inactive=False)]


@router.get("/organizations/{slug}/services", response_model=list[ServiceRead])
def services(slug: str, db: DB, branch_id: str | None = None, category_id: str | None = None) -> list[ServiceRead]:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import service_read

    rows = catalog.list_services(include_inactive=False, branch_id=branch_id, category_id=category_id)
    return [service_read(db, org, s, catalog) for s in rows if s.is_bookable_online]


@router.get("/organizations/{slug}/services/{service_id}", response_model=ServiceRead)
def service(slug: str, service_id: str, db: DB) -> ServiceRead:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import service_read

    svc = catalog.get_service(service_id)
    if not svc.is_active or not svc.is_bookable_online:
        raise NotFoundError("Service not found.")
    return service_read(db, org, svc, catalog)


@router.get("/organizations/{slug}/professionals", response_model=list[ProfessionalRead])
def professionals(slug: str, db: DB, branch_id: str | None = None, service_id: str | None = None) -> list[ProfessionalRead]:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import professional_read

    rows = catalog.list_professionals(include_inactive=False, branch_id=branch_id, service_id=service_id)
    return [_strip_private(professional_read(db, org, p)) for p in rows if p.is_bookable_online]


@router.get("/organizations/{slug}/professionals/{professional_id}", response_model=ProfessionalRead)
def professional(slug: str, professional_id: str, db: DB) -> ProfessionalRead:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import professional_read

    pro = catalog.get_professional(professional_id)
    if not pro.is_active or not pro.is_bookable_online:
        raise NotFoundError("Professional not found.")
    return _strip_private(professional_read(db, org, pro))


def _strip_private(data: ProfessionalRead) -> ProfessionalRead:
    data.email = None
    data.phone = None
    data.user_id = None
    return data


# ------------------------------------------------------------ booking flow
from datetime import date as _date  # noqa: E402

from fastapi import Depends, Query, Request, Response, status as _status  # noqa: E402

from app.api.deps import Meta, OptionalUser  # noqa: E402
from app.schemas.appointment import AppointmentCreate, AppointmentDetail, HoldCreate, HoldRead, PriceQuote, RescheduleRequest, StatusAction  # noqa: E402
from app.schemas.scheduling import AvailabilitySummary, DayAvailability  # noqa: E402
from app.security.rate_limit import limiter  # noqa: E402
from app.services.appointment_service import AppointmentService  # noqa: E402
from app.services.pricing_service import quote as _quote  # noqa: E402


@router.get("/organizations/{slug}/availability", response_model=DayAvailability)
def public_availability(slug: str, db: DB, service_id: str, branch_id: str, day: _date = Query(alias="date"), professional_id: str | None = None):
    from app.api.v1.scheduling import compute_day

    org, _ = _org(db, slug)
    return compute_day(db, org, service_id=service_id, branch_id=branch_id, professional_id=professional_id, day=day)


@router.get("/organizations/{slug}/availability/summary", response_model=list[AvailabilitySummary])
def public_availability_summary(slug: str, db: DB, service_id: str, branch_id: str, from_date: _date, to_date: _date, professional_id: str | None = None):
    from app.api.v1.scheduling import compute_summary

    org, _ = _org(db, slug)
    return compute_summary(db, org, service_id=service_id, branch_id=branch_id, professional_id=professional_id, from_date=from_date, to_date=to_date)


@router.get("/organizations/{slug}/quote", response_model=PriceQuote, summary="Server-side price for a service at a branch (optionally with a professional)")
def public_quote(slug: str, db: DB, service_id: str, branch_id: str, professional_id: str | None = None):
    org, catalog = _org(db, slug)
    q = _quote(catalog.get_service(service_id), catalog.get_branch(branch_id), catalog.get_professional(professional_id) if professional_id else None)
    return PriceQuote(currency=q.currency, subtotal_paise=q.subtotal_paise, discount_paise=q.discount_paise, tax_paise=q.tax_paise, total_amount_paise=q.total_amount_paise,
                      advance_due_paise=q.advance_due_paise, payment_mode=q.payment_mode, breakdown=q.breakdown)


@router.post("/organizations/{slug}/holds", response_model=HoldRead, status_code=_status.HTTP_201_CREATED, summary="Reserve a slot while the customer fills in details")
@limiter.limit("30/minute")
def public_hold(request: Request, response: Response, slug: str, payload: HoldCreate, db: DB, meta: Meta, user: OptionalUser):
    from app.api.v1.appointments import hold_read

    org, _ = _org(db, slug)
    service = AppointmentService(db, org, None, meta)
    customer = service.customers.for_user(user) if user else None
    return hold_read(db, service.create_hold(payload, session_key=payload.session_key, customer=customer))


@router.delete("/organizations/{slug}/holds/{hold_id}", response_model=dict)
def public_release_hold(slug: str, hold_id: str, db: DB, meta: Meta, session_key: str):
    org, _ = _org(db, slug)
    AppointmentService(db, org, None, meta).release_hold(hold_id, session_key=session_key)
    return {"detail": "Hold released."}


@router.post("/organizations/{slug}/appointments", response_model=AppointmentDetail, status_code=_status.HTTP_201_CREATED, summary="Book the held slot")
@limiter.limit("20/minute")
def public_book(request: Request, response: Response, slug: str, payload: AppointmentCreate, db: DB, meta: Meta, user: OptionalUser):
    from app.api.v1.appointments import appointment_detail

    org, _ = _org(db, slug)
    service = AppointmentService(db, org, user, meta)
    appt = service.create(payload, user=user, staff=False, session_key=payload.session_key)
    return appointment_detail(db, service.get(appt.public_id), include_token=True, service=service, viewer_is_customer=True)


@router.get("/organizations/{slug}/appointments/{reference}", response_model=AppointmentDetail, summary="Appointment status by reference + access token")
def public_appointment(slug: str, reference: str, db: DB, user: OptionalUser, access_token: str | None = None):
    from app.api.v1.appointments import appointment_detail

    org, _ = _org(db, slug)
    service = AppointmentService(db, org, user)
    appt = service.get_by_reference(reference, access_token, user)
    return appointment_detail(db, appt, service=service, viewer_is_customer=True)


@router.post("/organizations/{slug}/appointments/{reference}/cancel", response_model=AppointmentDetail)
def public_cancel(slug: str, reference: str, payload: StatusAction, db: DB, meta: Meta, user: OptionalUser, access_token: str | None = None):
    from app.api.v1.appointments import appointment_detail

    org, _ = _org(db, slug)
    service = AppointmentService(db, org, user, meta)
    appt = service.get_by_reference(reference, access_token, user)
    service.transition(appt, "cancel", reason=payload.reason, by_customer=True)
    return appointment_detail(db, service.get(appt.public_id), service=service, viewer_is_customer=True)


@router.post("/organizations/{slug}/appointments/{reference}/reschedule", response_model=AppointmentDetail)
def public_reschedule(slug: str, reference: str, payload: RescheduleRequest, db: DB, meta: Meta, user: OptionalUser, access_token: str | None = None, session_key: str | None = None):
    from app.api.v1.appointments import appointment_detail

    org, _ = _org(db, slug)
    service = AppointmentService(db, org, user, meta)
    appt = service.get_by_reference(reference, access_token, user)
    service.reschedule(appt, payload, by_customer=True, session_key=session_key)
    return appointment_detail(db, service.get(appt.public_id), service=service, viewer_is_customer=True)
