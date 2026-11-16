"""Customer management (staff) and the customer's own profile/family endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DB, AppSettings, CurrentUser, Meta, TenantContext, require_permission
from app.core.database import writes_on_read
from app.core.enums import OrganizationStatus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from app.core.observability import security_event
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.models import Customer, Organization
from app.schemas.common import Message
from app.schemas.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    DependentCreate,
    DependentRead,
    DependentUpdate,
    DocumentRead,
    NoteCreate,
    NoteRead,
    SelfProfileUpdate,
)
from app.security.rate_limit import limiter
from app.services.audit_service import record_audit
from app.services.customer_management_service import CustomerManagementService
from app.services.customer_service import CustomerService
from app.services.organization_service import OrganizationService
from app.services.privacy_service import check_bulk_access, check_export_allowed, require_recent_auth
from app.services.privacy_service import policy as privacy_policy

router = APIRouter(prefix="/customers", tags=["customers"])
ReadCust = Annotated[TenantContext, Depends(require_permission("customers:read"))]
WriteCust = Annotated[TenantContext, Depends(require_permission("customers:write"))]
ClinicalRead = Annotated[TenantContext, Depends(require_permission("customers:clinical_read"))]
ClinicalWrite = Annotated[TenantContext, Depends(require_permission("customers:clinical_write"))]


def _svc(db, ctx: TenantContext, meta) -> CustomerManagementService:
    svc = CustomerManagementService(db, ctx.organization, ctx.user, meta)
    if not ctx.has("appointments:read") and ctx.has("appointments:read_own") and privacy_policy(db, ctx.organization)["doctors_see_own_patients_only"]:
        from app.models import Professional

        pro = db.scalar(select(Professional.id).where(Professional.organization_id == ctx.organization.id, Professional.user_id == ctx.user.id,
                                                      Professional.deleted_at.is_(None)))
        svc.care_professional_id = pro if pro is not None else -1  # no linked doctor profile: no patients
    return svc


def _viewed(db, ctx: TenantContext, meta, customer, action: str, purpose: str | None = None) -> None:
    """Opening a patient's record is recorded (who, when, which part) and checked for unusual bulk access."""
    check_bulk_access(db, ctx.organization, ctx.user.id if ctx.user else None, customer.public_id)
    record_audit(db, action=action, actor=ctx.user, organization_id=ctx.organization.id, entity_type="customer", entity_id=customer.public_id,
                 purpose=purpose, meta=meta)


@router.get("", response_model=Page[CustomerRead])
def list_customers(
    db: DB, ctx: ReadCust, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(max_length=100)] = None, tag: Annotated[str | None, Query(max_length=40)] = None,
    segment: Annotated[str | None, Query(pattern=r"^(new_30d|upcoming|inactive_90d|returning)$")] = None, is_guest: bool | None = None,
):
    svc = _svc(db, ctx, meta)
    rows, total = svc.list(search=search, tag=tag, segment=segment, is_guest=is_guest, page=params.page, page_size=params.page_size)
    return Page(data=[svc.to_read(c) for c in svc.prepare_reads(rows)], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/export.csv", summary="Export customers as CSV (re-authentication, daily limit, audit-logged)")
@writes_on_read  # audit-logged
def export_customers(request: Request, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("customers:export"))], meta: Meta):
    require_recent_auth(db, request, ctx.organization, action="export")
    rows = db.scalar(select(func.count()).select_from(Customer).where(Customer.organization_id == ctx.organization.id, Customer.deleted_at.is_(None))) or 0
    check_export_allowed(db, ctx.organization, ctx.user.id, rows=rows)
    content = _svc(db, ctx, meta).export_csv()
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="customers-{ctx.organization.slug}.csv"'})


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.create(payload))


@router.get("/{customer_id}", response_model=CustomerRead)
@writes_on_read  # every opening is audit-logged
def get_customer(customer_id: str, db: DB, ctx: ReadCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    _viewed(db, ctx, meta, customer, "customer.viewed")
    svc.ensure_code(customer)
    return svc.to_read(customer, with_stats=True)


class RevealRequest(BaseModel):
    purpose: str | None = Field(default=None, max_length=200, description="Why the full details are needed (shown in the audit log)")


class RevealedDependent(BaseModel):
    id: str
    mobile: str | None


class RevealedContact(BaseModel):
    mobile: str | None
    email: str | None
    dependents: list[RevealedDependent]


@router.post("/{customer_id}/reveal", response_model=RevealedContact,
             summary="Show the full mobile number and email of one patient (re-authentication may be needed; audit-logged)")
@limiter.limit("30/minute")
def reveal_contact(request: Request, response: Response, customer_id: str, payload: RevealRequest, db: DB,
                   ctx: Annotated[TenantContext, Depends(require_permission("customers:reveal"))], meta: Meta):
    if getattr(request.state, "api_key", None) is not None:
        raise PermissionDenied("Revealing contact details is for people, not API keys.", code="api_key_not_allowed")
    if privacy_policy(db, ctx.organization)["reveal_requires_reauth"]:
        require_recent_auth(db, request, ctx.organization, action="reveal")
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    _viewed(db, ctx, meta, customer, "customer.contact_revealed", purpose=payload.purpose)
    security_event("contact_revealed")
    deps = svc.list_dependents(customer)
    return RevealedContact(mobile=customer.mobile, email=customer.email, dependents=[RevealedDependent(id=d.public_id, mobile=d.mobile) for d in deps])


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: str, payload: CustomerUpdate, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.update(svc.get(customer_id), payload), with_stats=True)


@router.delete("/{customer_id}", response_model=Message)
def delete_customer(customer_id: str, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete(svc.get(customer_id))
    return Message(detail="Customer deleted.")


class EraseRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500, description="Why the data is being erased (e.g. the customer's written request).")
    confirm: bool = Field(description="Must be true: erasure cannot be undone.")


@router.post("/{customer_id}/anonymize", response_model=Message, summary="Erase a customer's personal data (cannot be undone)")
def anonymize_customer(customer_id: str, payload: EraseRequest, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("customers:erase"))], meta: Meta):
    if not payload.confirm:
        raise ValidationFailed("Confirm that this erasure cannot be undone.", code="confirmation_required")
    svc = _svc(db, ctx, meta)
    svc.anonymize(svc.get(customer_id), payload.reason)
    return Message(detail="Customer data erased. Financial records are kept without personal details.")


# --------------------------------------------------------------- dependents
@router.get("/{customer_id}/dependents", response_model=list[DependentRead])
def list_dependents(customer_id: str, db: DB, ctx: ReadCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    c = svc.get(customer_id)
    return [svc.dependent_read(d, c) for d in svc.list_dependents(c)]


@router.post("/{customer_id}/dependents", response_model=DependentRead, status_code=status.HTTP_201_CREATED)
def add_dependent(customer_id: str, payload: DependentCreate, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    c = svc.get(customer_id)
    return svc.dependent_read(svc.add_dependent(c, payload), c)


@router.patch("/{customer_id}/dependents/{dependent_id}", response_model=DependentRead)
def update_dependent(customer_id: str, dependent_id: str, payload: DependentUpdate, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    c = svc.get(customer_id)
    return svc.dependent_read(svc.update_dependent(c, dependent_id, payload), c)


@router.delete("/{customer_id}/dependents/{dependent_id}", response_model=Message)
def delete_dependent(customer_id: str, dependent_id: str, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete_dependent(svc.get(customer_id), dependent_id)
    return Message(detail="Family member removed.")


# -------------------------------------------------------------------- notes
@router.get("/{customer_id}/notes", response_model=list[NoteRead])  # clinical notes; each opening is audit-logged
@writes_on_read  # access is audit-logged
def list_notes(customer_id: str, db: DB, ctx: ClinicalRead, meta: Meta, purpose: Annotated[str | None, Query(max_length=200)] = None):
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    check_bulk_access(db, ctx.organization, ctx.user.id if ctx.user else None, customer.public_id)
    return svc.list_notes(customer, purpose=purpose)


@router.post("/{customer_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def add_note(customer_id: str, payload: NoteCreate, db: DB, ctx: ClinicalWrite, meta: Meta):
    svc = _svc(db, ctx, meta)
    c = svc.get(customer_id)
    row = svc.add_note(c, payload)
    return NoteRead(id=row.public_id, note_type=row.note_type, body=payload.body, is_sensitive=row.is_sensitive, appointment_id=payload.appointment_id,
                    author_name=ctx.user.full_name, created_at=row.created_at, updated_at=row.updated_at)


@router.delete("/{customer_id}/notes/{note_id}", response_model=Message)
def delete_note(customer_id: str, note_id: str, db: DB, ctx: ClinicalWrite, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete_note(svc.get(customer_id), note_id)
    return Message(detail="Note deleted.")


# ---------------------------------------------------------------- documents
@router.get("/{customer_id}/documents", response_model=list[DocumentRead])
@writes_on_read  # every opening is audit-logged
def list_documents(customer_id: str, db: DB, ctx: ClinicalRead, meta: Meta):
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    _viewed(db, ctx, meta, customer, "customer.documents_viewed")
    return [svc.document_read(d) for d in svc.list_documents(customer)]


@router.post("/{customer_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    customer_id: str, db: DB, ctx: ClinicalWrite, meta: Meta, settings: AppSettings,
    file: UploadFile = File(...), title: str = Form(""), document_type: str = Form("other"), appointment_id: str | None = Form(None),
):
    svc = _svc(db, ctx, meta)
    c = svc.get(customer_id)
    data = file.file.read()
    row = svc.add_document(c, data=data, title=title or (file.filename or "Document"), document_type=document_type[:32], appointment_id=appointment_id or None, max_mb=settings.max_upload_size_mb)
    return svc.document_read(row)


def _safe_filename(title: str, mime: str) -> str:
    import re as _re

    from app.core.storage import EXTENSIONS

    base = _re.sub(r"[^A-Za-z0-9 ._-]+", "_", title).strip(" ._")[:80] or "document"
    ext = EXTENSIONS.get(mime)
    return base if not ext or base.lower().endswith("." + ext) else f"{base}.{ext}"


def _document_response(row, handle) -> StreamingResponse:
    return StreamingResponse(handle, media_type=row.mime_type, headers={
        "Content-Disposition": f'inline; filename="{_safe_filename(row.title, row.mime_type)}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{customer_id}/documents/{document_id}/download", summary="Download a document (re-authentication; audit-logged)")
@writes_on_read  # access is audit-logged
def download_document(request: Request, customer_id: str, document_id: str, db: DB, ctx: ClinicalRead, meta: Meta,
                      purpose: Annotated[str | None, Query(max_length=200)] = None):
    require_recent_auth(db, request, ctx.organization, action="document")
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    check_bulk_access(db, ctx.organization, ctx.user.id, customer.public_id)
    row, handle = svc.open_document(customer, document_id, purpose=purpose)
    return _document_response(row, handle)


@router.get("/{customer_id}/summary.pdf", summary="Controlled PDF summary of one patient (watermarked; re-authentication; audit-logged)")
@writes_on_read  # audit-logged
def patient_summary_pdf(request: Request, customer_id: str, db: DB, ctx: ReadCust, meta: Meta):
    from app.core.pdf import build_pdf
    from app.core.time import utcnow
    from app.models import Appointment, Professional, Service
    from app.services.privacy_service import mask_email, mask_mobile

    require_recent_auth(db, request, ctx.organization, action="export")
    check_export_allowed(db, ctx.organization, ctx.user.id)
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    check_bulk_access(db, ctx.organization, ctx.user.id, customer.public_id)
    full = ctx.has("customers:reveal")
    now = utcnow()
    sid = (getattr(request.state, "session_public_id", "") or "").replace("-", "")[:6].upper()
    user_ref = "U-" + ctx.user.public_id.replace("-", "")[:8].upper()
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    lines: list[tuple[str, str]] = [("h", "Patient"), ("", f"Name: {customer.full_name}"), ("", f"Patient code: {customer.customer_code or '-'}"),
                                    ("", f"Mobile: {(customer.mobile if full else mask_mobile(customer.mobile)) or '-'}"),
                                    ("", f"Email: {(customer.email if full else mask_email(customer.email)) or '-'}"),
                                    ("", f"Date of birth: {customer.date_of_birth or '-'}   Gender: {customer.gender or '-'}   Blood group: {customer.blood_group or '-'}"),
                                    ("", ""), ("h", "Appointments (latest 30)")]
    appts = db.execute(select(Appointment.start_at, Appointment.status, Service.name, Professional.display_name)
                       .join(Service, Service.id == Appointment.service_id).join(Professional, Professional.id == Appointment.professional_id)
                       .where(Appointment.organization_id == ctx.organization.id, Appointment.customer_id == customer.id)
                       .order_by(Appointment.start_at.desc()).limit(30)).all()
    lines += [("", f"{a.start_at:%Y-%m-%d %H:%M}  {a.name}  with {a.display_name}  ({str(a.status).replace('_', ' ')})") for a in appts] or [("", "None.")]
    if ctx.has("customers:clinical_read"):
        lines += [("", ""), ("h", "Clinical notes")]
        notes = svc.list_notes(customer, purpose="PDF summary export")
        for n in notes:
            lines += [("b", f"{n.created_at:%Y-%m-%d}  {n.note_type}  ({n.author_name or '-'})"), ("", n.body)]
        if not notes:
            lines.append(("", "None."))
    pdf = build_pdf(title=f"Patient summary - {ctx.organization.name}", lines=lines,
                    watermark=f"CONFIDENTIAL  {user_ref}  {stamp}  S-{sid}",
                    footer=f"Confidential patient record. Exported by {user_ref} (session S-{sid}) at {stamp}. Do not forward.")
    record_audit(db, action="customer.summary_exported", actor=ctx.user, organization_id=ctx.organization.id, entity_type="customer",
                 entity_id=customer.public_id, after={"format": "pdf", "clinical": ctx.has("customers:clinical_read"), "full_contact": full}, meta=meta)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="patient-{customer.customer_code or customer.public_id[:8]}.pdf"',
        "Cache-Control": "private, no-store"})


LINK_SECONDS = 60


class DocumentLink(BaseModel):
    url: str
    expires_in: int


@router.post("/{customer_id}/documents/{document_id}/link", response_model=DocumentLink,
             summary="A download link for one document that works for 60 seconds, only for you, only in this session")
def document_link(request: Request, customer_id: str, document_id: str, db: DB, ctx: ClinicalRead, meta: Meta):
    import base64
    import json
    import time

    from app.security.crypto import keyed_hash

    require_recent_auth(db, request, ctx.organization, action="document")
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    row = svc.get_document(customer, document_id)
    check_export_allowed(db, ctx.organization, ctx.user.id)
    body = base64.urlsafe_b64encode(json.dumps({
        "o": ctx.organization.public_id, "c": customer.public_id, "d": row.public_id, "u": ctx.user.public_id,
        "s": getattr(request.state, "session_public_id", None), "e": int(time.time()) + LINK_SECONDS,
    }, separators=(",", ":")).encode()).decode().rstrip("=")
    record_audit(db, action="customer.document_link_created", actor=ctx.user, organization_id=ctx.organization.id, entity_type="customer",
                 entity_id=customer.public_id, after={"document_id": row.public_id, "expires_in": LINK_SECONDS}, meta=meta)
    return DocumentLink(url=f"/api/v1/files/{body}.{keyed_hash(body, 'download')}", expires_in=LINK_SECONDS)


files_router = APIRouter(prefix="/files", tags=["customers"])


@files_router.get("/{token}", summary="Open a signed document link (see POST .../documents/{id}/link)")
@writes_on_read  # access is audit-logged
def open_signed_document(token: str, db: DB, meta: Meta):
    import base64
    import hmac
    import json
    import time

    from app.core.exceptions import AuthenticationError
    from app.core.time import utcnow
    from app.models import OrganizationMembership, User, UserSession
    from app.security.crypto import keyed_hash
    from app.security.permissions import PERMISSIONS

    body, _, sig = token.rpartition(".")
    if not body or not hmac.compare_digest(sig, keyed_hash(body, "download")):
        raise NotFoundError("This link is not valid.", code="link_invalid")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if data["e"] < time.time():
        raise NotFoundError("This link has expired. Open the document again from the patient's record.", code="link_expired")
    session = db.scalar(select(UserSession).where(UserSession.public_id == data.get("s")))
    user = db.scalar(select(User).where(User.public_id == data["u"]))
    if session is None or user is None or session.user_id != user.id or session.revoked_at is not None or session.locked_at is not None \
            or session.expires_at < utcnow():
        raise AuthenticationError("Sign in again to open this document.", code="session_revoked")
    org = db.scalar(select(Organization).where(Organization.public_id == data["o"]))
    if org is None:
        raise NotFoundError("This link is not valid.", code="link_invalid")
    membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == org.id,
                                                                OrganizationMembership.user_id == user.id))
    permissions = set(PERMISSIONS) if user.is_platform_admin else ({p.code for p in membership.role.permissions} if membership and membership.role else set())
    ctx = TenantContext(user=user, organization=org, membership=membership, permissions=permissions, is_platform_admin=user.is_platform_admin)
    if not ctx.has("customers:clinical_read"):  # access is checked again now, not only when the link was made
        raise PermissionDenied("You no longer have access to this document.", code="permission_denied")
    from app.core.branch_scope import set_branch_scope

    set_branch_scope(db, membership.branch_id if membership is not None else None)
    svc = _svc(db, ctx, meta)
    row, handle = svc.open_document(svc.get(data["c"]), data["d"], purpose="signed link")
    return _document_response(row, handle)


@router.delete("/{customer_id}/documents/{document_id}", response_model=Message)
def delete_document(customer_id: str, document_id: str, db: DB, ctx: ClinicalWrite, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete_document(svc.get(customer_id), document_id)
    return Message(detail="Document deleted.")


# ======================================================= customer self-service
self_router = APIRouter(prefix="/customer", tags=["customer"])


def _own(db, user, org_public_id: str, *, create: bool = True) -> tuple[Organization, Customer | None, CustomerManagementService]:
    """The signed-in user's own customer record at this organization.

    Reads never create a record (otherwise merely opening a clinic's booking page would add the visitor to that
    clinic's patient list). A write may create one, but only at an organization that is open for business."""
    org = OrganizationService(db).get_or_404(org_public_id)
    customer = db.scalar(select(Customer).where(Customer.organization_id == org.id, Customer.user_id == user.id, Customer.deleted_at.is_(None)))
    if customer is None and create:
        if org.status != OrganizationStatus.ACTIVE:
            raise NotFoundError("Organization not found.")
        customer = CustomerService(db, org).for_user(user)
    if not bool(OrganizationService(db).get_settings(org, "privacy")["privacy"].get("allow_customer_self_update", True)):
        raise PermissionDenied("This organization does not allow profile self-service.", code="self_update_disabled")
    return org, customer, CustomerManagementService(db, org, user)


@self_router.get("/organizations/{organization_id}/profile", response_model=CustomerRead, summary="My record in this organization")
def my_profile(organization_id: str, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id, create=False)
    if customer is None:
        raise NotFoundError("You have no record with this organization yet.", code="no_customer_record")
    return svc.to_read(customer, with_stats=True)


@self_router.patch("/organizations/{organization_id}/profile", response_model=CustomerRead)
def update_my_profile(organization_id: str, payload: SelfProfileUpdate, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id)
    return svc.to_read(svc.update_self(customer, payload), with_stats=True)


@self_router.get("/organizations/{organization_id}/dependents", response_model=list[DependentRead])
def my_dependents(organization_id: str, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id, create=False)
    if customer is None:
        return []
    return [svc.dependent_read(d, customer) for d in svc.list_dependents(customer)]


@self_router.post("/organizations/{organization_id}/dependents", response_model=DependentRead, status_code=status.HTTP_201_CREATED)
def add_my_dependent(organization_id: str, payload: DependentCreate, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id)
    return svc.dependent_read(svc.add_dependent(customer, payload), customer)


@self_router.patch("/organizations/{organization_id}/dependents/{dependent_id}", response_model=DependentRead)
def update_my_dependent(organization_id: str, dependent_id: str, payload: DependentUpdate, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id)
    return svc.dependent_read(svc.update_dependent(customer, dependent_id, payload), customer)


@self_router.delete("/organizations/{organization_id}/dependents/{dependent_id}", response_model=Message)
def delete_my_dependent(organization_id: str, dependent_id: str, db: DB, user: CurrentUser):
    _, customer, svc = _own(db, user, organization_id)
    svc.delete_dependent(customer, dependent_id)
    return Message(detail="Family member removed.")


@self_router.get("/organizations", response_model=list[dict], summary="Organizations where I have a customer record")
def my_organizations(db: DB, user: CurrentUser):
    from sqlalchemy import select

    rows = db.execute(select(Organization.public_id, Organization.name, Organization.slug).join(Customer, Customer.organization_id == Organization.id).where(Customer.user_id == user.id, Customer.deleted_at.is_(None), Organization.deleted_at.is_(None))).all()
    return [{"id": r[0], "name": r[1], "slug": r[2]} for r in rows]
