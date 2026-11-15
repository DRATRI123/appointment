"""Unauthenticated catalogue for the public booking website. Only active, bookable data is exposed."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.deps import DB
from app.core.exceptions import NotFoundError
from app.models import Organization, ServiceCategory
from app.schemas.catalog import BranchRead, CategoryRead, ProfessionalRead, ServiceRead
from app.schemas.common import APIModel
from app.schemas.organization import OrganizationRead
from app.schemas.website import PublicWebsite
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
    out = {ns: all_settings.get(ns, {}) for ns in ("branding", "booking", "cancellation", "legal", "general")}
    # Only the flag the booking page needs; the rest of the notification config stays private.
    out["messaging"] = {"whatsapp_enabled": bool(all_settings.get("notification", {}).get("whatsapp_enabled"))}
    return out


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

from fastapi import Query, Request, Response  # noqa: E402
from fastapi import status as _status  # noqa: E402

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


@router.get("/organizations/{slug}/quote", response_model=PriceQuote, summary="Server-side price for a service at a branch (optionally with a professional and coupon)")
def public_quote(slug: str, db: DB, service_id: str, branch_id: str, professional_id: str | None = None, coupon_code: str | None = None):
    org, catalog = _org(db, slug)
    service, branch = catalog.get_service(service_id), catalog.get_branch(branch_id)
    pro = catalog.get_professional(professional_id) if professional_id else None
    coupon = None
    if coupon_code:
        from app.services.coupon_service import CouponService

        base = _quote(service, branch, pro)
        coupon = CouponService(db, org).validate(coupon_code, service=service, price_paise=base.subtotal_paise - base.discount_paise, customer_id=None)
    q = _quote(service, branch, pro, coupon=coupon)
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


class VerificationOptions(APIModel):
    required: bool
    channels: list[str] = Field(description="Methods the clinic enabled and can deliver, in its preferred order")
    default_channel: str | None
    code_length: int
    resend_cooldown_seconds: int


class VerificationStart(APIModel):
    channel: str = Field(pattern=r"^(sms|whatsapp|email)$")
    destination: str = Field(min_length=3, max_length=254, description="Mobile number for sms/whatsapp, email address for email")
    hold_id: str = Field(max_length=64)
    session_key: str = Field(min_length=8, max_length=64)


class VerificationSession(APIModel):
    session_key: str = Field(min_length=8, max_length=64)


class VerificationCode(VerificationSession):
    code: str = Field(pattern=r"^\d{4,8}$")


class VerificationChallenge(APIModel):
    challenge_id: str
    channel: str
    destination: str = Field(description="Masked, e.g. +91•••••210")
    code_length: int
    expires_in_seconds: int
    resend_after_seconds: int
    resends_left: int


class VerificationResult(APIModel):
    verification_token: str
    channel: str
    destination: str
    expires_in_seconds: int


@router.get("/organizations/{slug}/verification", response_model=VerificationOptions, summary="Which verification methods the booking page may offer")
def verification_options(slug: str, db: DB):
    from app.services.otp import booking_verification_required, load_policy
    from app.services.otp.otp_service import available_channels

    org, _ = _org(db, slug)
    policy = load_policy(db, org)
    channels = available_channels(db, org, policy)
    default = policy.get("default_channel") if policy.get("default_channel") in channels else (channels[0] if channels else None)
    ordered = ([default] if default else []) + [c for c in channels if c != default]
    return VerificationOptions(required=booking_verification_required(db, org), channels=ordered, default_channel=default,
                               code_length=policy["code_length"], resend_cooldown_seconds=policy["resend_cooldown_seconds"])


@router.post("/organizations/{slug}/verification/start", response_model=VerificationChallenge, summary="Send a one-time code by SMS, WhatsApp or email")
@limiter.limit("5/minute;30/hour")
def verification_start(request: Request, response: Response, slug: str, payload: VerificationStart, db: DB, meta: Meta):
    from app.services.otp import OTPService

    org, _ = _org(db, slug)
    return OTPService(db, org, meta).start(channel=payload.channel, destination=payload.destination, hold_id=payload.hold_id, session_key=payload.session_key)


@router.post("/organizations/{slug}/verification/{challenge_id}/resend", response_model=VerificationChallenge, summary="Send a new code for the same request")
@limiter.limit("5/minute;20/hour")
def verification_resend(request: Request, response: Response, slug: str, challenge_id: str, payload: VerificationSession, db: DB, meta: Meta):
    from app.services.otp import OTPService

    org, _ = _org(db, slug)
    return OTPService(db, org, meta).resend(challenge_id, payload.session_key)


@router.post("/organizations/{slug}/verification/{challenge_id}/verify", response_model=VerificationResult, summary="Check the code; returns the token the booking needs")
@limiter.limit("10/minute")
def verification_verify(request: Request, response: Response, slug: str, challenge_id: str, payload: VerificationCode, db: DB, meta: Meta):
    from app.services.otp import OTPService

    org, _ = _org(db, slug)
    return OTPService(db, org, meta).verify(challenge_id, payload.code, payload.session_key)


class EmbedPolicy(APIModel):
    allowed_origins: list[str]
    booking_page_enabled: bool


@router.get("/organizations/{slug}/website", response_model=PublicWebsite, summary="The clinic's published website (or a starting site built from its profile)")
def public_website(slug: str, db: DB, response: Response):
    from app.services.website_service import WebsiteService

    org, _ = _org(db, slug)
    # Always revalidate: after the clinic publishes, visitors (and the admin checking) must see the new version at once.
    response.headers["Cache-Control"] = "no-cache"
    return WebsiteService(db, org).public()


class SiteEvent(APIModel):
    metric: str = Field(pattern=r"^(page_view|book_click|booking_view)$")
    key: str = Field(default="", max_length=80)
    source: str = Field(default="", max_length=64)


@router.post("/organizations/{slug}/events", status_code=204, summary="Count a page view or Book click (no cookies, no personal data)")
@limiter.limit("120/minute")
def site_event(request: Request, response: Response, slug: str, payload: SiteEvent, db: DB):
    from app.services.website_analytics_service import WebsiteAnalyticsService

    org, _ = _org(db, slug)
    WebsiteAnalyticsService(db, org).record(payload.metric, payload.key, payload.source)
    return Response(status_code=204)


@router.get("/organizations/{slug}/embed-policy", response_model=EmbedPolicy, summary="Websites allowed to show this booking page in an iframe")
def embed_policy(slug: str, db: DB, response: Response):
    org, _ = _org(db, slug)
    settings = OrganizationService(db).get_settings(org)
    response.headers["Cache-Control"] = "public, max-age=60"
    return EmbedPolicy(allowed_origins=list(settings.get("embed", {}).get("allowed_origins") or []),
                       booking_page_enabled=bool(settings.get("general", {}).get("booking_page_enabled", True)))


@router.delete("/organizations/{slug}/holds/{hold_id}", response_model=dict)
def public_release_hold(slug: str, hold_id: str, db: DB, meta: Meta, session_key: str):
    org, _ = _org(db, slug)
    AppointmentService(db, org, None, meta).release_hold(hold_id, session_key=session_key)
    return {"detail": "Hold released."}


@router.post("/organizations/{slug}/appointments", response_model=AppointmentDetail, status_code=_status.HTTP_201_CREATED, summary="Book the held slot")
@limiter.limit("20/minute")
def public_book(request: Request, response: Response, slug: str, payload: AppointmentCreate, db: DB, meta: Meta, user: OptionalUser):
    from app.api.v1.appointments import appointment_detail
    from app.services.otp import check_booking_token

    org, _ = _org(db, slug)
    check_booking_token(db, org, hold_id=payload.hold_id, session_key=payload.session_key, customer_mobile=payload.customer.mobile,
                        customer_email=payload.customer.email, token=payload.verification_token or payload.mobile_verification_token, user=user)
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


# ---------------------------------------------------------- booking forms
from fastapi import File, UploadFile  # noqa: E402

from app.api.deps import AppSettings  # noqa: E402
from app.core.storage import get_storage, validate_upload  # noqa: E402
from app.schemas.booking_form import PublicForm  # noqa: E402
from app.services.form_service import FormService  # noqa: E402

FORM_FILE_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


@router.get("/organizations/{slug}/booking-form", response_model=PublicForm | None, summary="The form to show for a service/branch (null when none)")
def public_booking_form(slug: str, db: DB, service_id: str | None = None, branch_id: str | None = None):
    org, catalog = _org(db, slug)
    service = catalog.get_service(service_id) if service_id else None
    branch = catalog.get_branch(branch_id) if branch_id else None
    form = FormService(db, org).resolve(service, branch)
    return FormService(db, org).public_form(form) if form else None


@router.post("/organizations/{slug}/booking-form-files", summary="Upload a file for a booking-form file field (private storage)")
@limiter.limit("20/minute")
def public_form_file(request: Request, response: Response, slug: str, db: DB, settings: AppSettings, file: UploadFile = File(...)):
    org, _ = _org(db, slug)
    data = file.file.read()
    mime = validate_upload(data, allowed=FORM_FILE_TYPES, max_mb=settings.max_upload_size_mb)
    stored = get_storage().save(scope=f"org/{org.public_id}/form-files", visibility="private", data=data, mime_type=mime)
    return {"key": stored.key, "name": (file.filename or "file")[:160], "mime_type": stored.mime_type, "size_bytes": stored.size_bytes}


# ------------------------------------------------------------- UPI checkout
from datetime import datetime as _datetime  # noqa: E402

from fastapi import Form  # noqa: E402

from app.schemas.payment import Checkout  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402


def _payment_for(db, slug: str, reference: str, access_token: str | None, user):
    org, _ = _org(db, slug)
    appt = AppointmentService(db, org, user).get_by_reference(reference, access_token, user)
    svc = PaymentService(db, org, user)
    payment = svc.current_for_appointment(appt)
    return org, appt, svc, payment


@router.get("/organizations/{slug}/appointments/{reference}/payment", response_model=Checkout | None,
            summary="UPI checkout for an appointment: QR, UPI ID, app links and submission status (null when nothing is due)")
def public_checkout(slug: str, reference: str, db: DB, user: OptionalUser, access_token: str | None = None):
    _, _, svc, payment = _payment_for(db, slug, reference, access_token, user)
    return svc.checkout(payment) if payment else None


@router.post("/organizations/{slug}/appointments/{reference}/payment/submit", response_model=Checkout,
             summary="Submit the UTR (and optional screenshot) after paying. This never confirms the payment by itself.")
@limiter.limit("10/minute")
def public_submit_payment(
    request: Request, response: Response, slug: str, reference: str, db: DB, user: OptionalUser, meta: Meta,
    access_token: str | None = None,
    utr: str = Form(..., max_length=64), transaction_reference: str | None = Form(None, max_length=128), paid_at: _datetime | None = Form(None),
    payer_upi_id: str | None = Form(None, max_length=120), notes: str | None = Form(None, max_length=2000), screenshot: UploadFile | None = File(None),
):
    org, appt, _, payment = _payment_for(db, slug, reference, access_token, user)
    svc = PaymentService(db, org, user, meta)
    if payment is None:
        from app.core.exceptions import ConflictError

        raise ConflictError("Nothing is due for this appointment.", code="nothing_due")
    data = screenshot.file.read() if screenshot is not None else None
    svc.submit(payment, utr=utr, transaction_reference=transaction_reference, paid_at=paid_at, payer_upi_id=payer_upi_id, notes=notes, screenshot=data or None,
               submitted_ip=meta.ip_address)
    return svc.checkout(payment)
