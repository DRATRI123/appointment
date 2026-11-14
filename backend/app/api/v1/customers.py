"""Customer management (staff) and the customer's own profile/family endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, AppSettings, CurrentUser, Meta, TenantContext, require_permission
from app.core.enums import OrganizationStatus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
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
from app.services.customer_management_service import CustomerManagementService
from app.services.customer_service import CustomerService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/customers", tags=["customers"])
ReadCust = Annotated[TenantContext, Depends(require_permission("customers:read"))]
WriteCust = Annotated[TenantContext, Depends(require_permission("customers:write"))]
ClinicalRead = Annotated[TenantContext, Depends(require_permission("customers:clinical_read"))]
ClinicalWrite = Annotated[TenantContext, Depends(require_permission("customers:clinical_write"))]


def _svc(db, ctx: TenantContext, meta) -> CustomerManagementService:
    return CustomerManagementService(db, ctx.organization, ctx.user, meta)


@router.get("", response_model=Page[CustomerRead])
def list_customers(
    db: DB, ctx: ReadCust, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(max_length=100)] = None, tag: Annotated[str | None, Query(max_length=40)] = None,
    segment: Annotated[str | None, Query(pattern=r"^(new_30d|upcoming|inactive_90d|returning)$")] = None, is_guest: bool | None = None,
):
    svc = _svc(db, ctx, meta)
    rows, total = svc.list(search=search, tag=tag, segment=segment, is_guest=is_guest, page=params.page, page_size=params.page_size)
    return Page(data=[svc.to_read(c) for c in svc.prepare_reads(rows)], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/export.csv", summary="Export customers as CSV")
def export_customers(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("customers:export"))], meta: Meta):
    content = _svc(db, ctx, meta).export_csv()
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="customers-{ctx.organization.slug}.csv"'})


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: DB, ctx: WriteCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.create(payload))


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: str, db: DB, ctx: ReadCust, meta: Meta):
    svc = _svc(db, ctx, meta)
    customer = svc.get(customer_id)
    svc.ensure_code(customer)
    return svc.to_read(customer, with_stats=True)


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
@router.get("/{customer_id}/notes", response_model=list[NoteRead])
def list_notes(customer_id: str, db: DB, ctx: ClinicalRead, meta: Meta, purpose: Annotated[str | None, Query(max_length=200)] = None):
    svc = _svc(db, ctx, meta)
    return svc.list_notes(svc.get(customer_id), purpose=purpose)


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
def list_documents(customer_id: str, db: DB, ctx: ClinicalRead, meta: Meta):
    svc = _svc(db, ctx, meta)
    return [svc.document_read(d) for d in svc.list_documents(svc.get(customer_id))]


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


@router.get("/{customer_id}/documents/{document_id}/download", summary="Download a document (access is audit-logged)")
def download_document(customer_id: str, document_id: str, db: DB, ctx: ClinicalRead, meta: Meta, purpose: Annotated[str | None, Query(max_length=200)] = None):
    svc = _svc(db, ctx, meta)
    row, handle = svc.open_document(svc.get(customer_id), document_id, purpose=purpose)
    return StreamingResponse(handle, media_type=row.mime_type, headers={"Content-Disposition": f'inline; filename="{row.title}"', "Cache-Control": "private, no-store"})


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
