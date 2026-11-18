"""Patient help desk (app/services/helpdesk_service.py).

* ``/customer/organizations/{org_id}/requests`` … the signed-in patient's own requests at one clinic.
* ``/helpdesk/…`` … the clinic's inbox (``helpdesk:read`` to see, ``helpdesk:write`` to answer and change).

Messages may carry one attachment (image or PDF), sent as multipart form data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import Field

from app.api.deps import DB, CurrentUser, Meta, TenantContext, require_permission
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.schemas.common import APIModel
from app.security.rate_limit import limiter
from app.services.helpdesk_service import CATEGORIES, PRIORITIES, STATUSES, HelpdeskService
from app.services.organization_service import OrganizationService

patient_router = APIRouter(prefix="/customer/organizations/{org_id}/requests", tags=["help desk (patient)"])
public_router = APIRouter(prefix="/public/organizations/{slug}/help", tags=["help desk (patient)"])
router = APIRouter(prefix="/helpdesk", tags=["help desk"])

ReadDesk = Annotated[TenantContext, Depends(require_permission("helpdesk:read"))]
WriteDesk = Annotated[TenantContext, Depends(require_permission("helpdesk:write"))]


class AppointmentRef(APIModel):
    reference: str
    start_at: datetime
    timezone: str
    service_name: str


class Person(APIModel):
    id: str
    name: str


class TicketRead(APIModel):
    id: str
    number: int
    subject: str
    category: str
    category_label: str
    status: str
    created_at: datetime
    last_activity_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    rating: int | None
    unread: bool
    appointment: AppointmentRef | None


class StaffTicketRead(TicketRead):
    priority: str
    customer: Person | None
    assigned_to: Person | None
    branch_name: str | None
    first_response_due_at: datetime | None
    first_response_at: datetime | None
    overdue: bool


class Attachment(APIModel):
    name: str | None
    mime: str | None
    size: int | None


class MessageRead(APIModel):
    id: str
    author_kind: str
    author_name: str
    internal: bool
    body: str
    created_at: datetime
    attachment: Attachment | None


class TicketDetail(TicketRead):
    messages: list[MessageRead]


class StaffTicketDetail(StaffTicketRead):
    messages: list[MessageRead]


class Options(APIModel):
    enabled: bool
    categories: dict[str, str]


class Resolve(APIModel):
    rating: int | None = Field(default=None, ge=1, le=5)


class TicketUpdate(APIModel):
    status: str | None = Field(default=None, pattern="^(" + "|".join(STATUSES) + ")$")
    priority: str | None = Field(default=None, pattern="^(" + "|".join(PRIORITIES) + ")$")
    category: str | None = Field(default=None, pattern="^(" + "|".join(CATEGORIES) + ")$")
    assigned_to: str | None = Field(default=None, max_length=36, description="User id of a member who answers requests")
    unassign: bool = False


def _file(upload: UploadFile | None) -> tuple[bytes, str] | None:
    if upload is None or not upload.filename:
        return None
    return upload.file.read(), upload.filename


def _attachment_response(msg, handle) -> StreamingResponse:
    disposition = "inline" if (msg.attachment_mime or "").startswith("image/") else f'attachment; filename="{msg.attachment_name or "attachment"}"'
    return StreamingResponse(handle, media_type=msg.attachment_mime or "application/octet-stream",
                             headers={"Cache-Control": "private, no-store", "Content-Disposition": disposition, "X-Content-Type-Options": "nosniff"})


# ============================================================================================================ patient
def _patient(db, user, org_id: str, meta) -> HelpdeskService:
    return HelpdeskService(db, OrganizationService(db).get_or_404(org_id), user, meta)


def _detail(svc: HelpdeskService, ticket, *, staff: bool) -> dict[str, Any]:
    return {**svc.read(ticket, staff=staff), "messages": [svc.message_read(m, staff=staff) for m in svc.messages(ticket, staff=staff)]}


@patient_router.get("", response_model=list[TicketRead], summary="My requests at this clinic")
def my_requests(org_id: str, db: DB, user: CurrentUser, meta: Meta) -> list[dict]:
    svc = _patient(db, user, org_id, meta)
    return [svc.read(t, staff=False) for t in svc.patient_list()]


@patient_router.post("", response_model=TicketDetail, status_code=201, summary="Ask the clinic a question")
@limiter.limit("10/hour")
def create_request(request: Request, response: Response, org_id: str, db: DB, user: CurrentUser, meta: Meta,
                   category: Annotated[str, Form(max_length=32)], subject: Annotated[str, Form(max_length=200)],
                   body: Annotated[str, Form(max_length=5000)], appointment_reference: Annotated[str | None, Form(max_length=80)] = None,
                   file: Annotated[UploadFile | None, File()] = None) -> dict:
    svc = _patient(db, user, org_id, meta)
    ticket = svc.patient_create(category=category, subject=subject, body=body, appointment_reference=appointment_reference or None, file=_file(file))
    return _detail(svc, ticket, staff=False)


@patient_router.get("/{ticket_id}", response_model=TicketDetail, summary="One of my requests, with the conversation")
def my_request(org_id: str, ticket_id: str, db: DB, user: CurrentUser, meta: Meta) -> dict:
    svc = _patient(db, user, org_id, meta)
    ticket = svc.patient_get(ticket_id)
    svc.mark_read(ticket, staff=False)
    return _detail(svc, ticket, staff=False)


@patient_router.post("/{ticket_id}/messages", response_model=TicketDetail, summary="Reply to the clinic")
@limiter.limit("30/minute")
def reply(request: Request, response: Response, org_id: str, ticket_id: str, db: DB, user: CurrentUser, meta: Meta,
          body: Annotated[str, Form(max_length=5000)], file: Annotated[UploadFile | None, File()] = None) -> dict:
    svc = _patient(db, user, org_id, meta)
    ticket = svc.patient_get(ticket_id)
    svc.patient_reply(ticket, body, _file(file))
    return _detail(svc, ticket, staff=False)


@patient_router.post("/{ticket_id}/resolve", response_model=TicketDetail, summary="My question is answered (and how helpful it was, 1-5)")
def resolve(org_id: str, ticket_id: str, payload: Resolve, db: DB, user: CurrentUser, meta: Meta) -> dict:
    svc = _patient(db, user, org_id, meta)
    ticket = svc.patient_resolve(svc.patient_get(ticket_id), payload.rating)
    return _detail(svc, ticket, staff=False)


@patient_router.get("/{ticket_id}/messages/{message_id}/attachment", summary="An attachment in my conversation")
def my_attachment(org_id: str, ticket_id: str, message_id: str, db: DB, user: CurrentUser, meta: Meta):
    svc = _patient(db, user, org_id, meta)
    msg, handle = svc.open_attachment(svc.patient_get(ticket_id), message_id, staff=False)
    return _attachment_response(msg, handle)


@public_router.get("", response_model=Options, summary="Public: does this clinic take questions online, and about what")
def options(slug: str, db: DB) -> Options:
    from app.services.helpdesk_service import policy

    org = OrganizationService(db).get_by_slug_public(slug)
    return Options(enabled=bool(policy(db, org).get("enabled", True)), categories=CATEGORIES)


# ============================================================================================================== staff
def _staff(db, ctx: TenantContext, meta) -> HelpdeskService:
    return HelpdeskService(db, ctx.organization, ctx.user, meta)


@router.get("/summary", summary="Counts for the inbox: open, waiting for the patient, unassigned, overdue, response time, rating")
def summary(db: DB, ctx: ReadDesk, meta: Meta) -> dict:
    return _staff(db, ctx, meta).summary()


@router.get("/agents", response_model=list[Person], summary="Members who can answer requests")
def agents(db: DB, ctx: ReadDesk, meta: Meta) -> list[dict]:
    return _staff(db, ctx, meta).agents()


@router.get("/tickets", response_model=Page[StaffTicketRead], summary="The inbox")
def tickets(db: DB, ctx: ReadDesk, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
            status: Annotated[str, Query(pattern=r"^(active|overdue|all|open|pending_customer|resolved|closed)$")] = "active",
            assigned: Annotated[str, Query(pattern=r"^(any|me|unassigned)$")] = "any",
            category: Annotated[str | None, Query(max_length=32)] = None, search: Annotated[str | None, Query(max_length=100)] = None):
    svc = _staff(db, ctx, meta)
    rows, total = svc.staff_list(status=status, assigned=assigned, category=category, search=search, page=params.page, page_size=params.page_size)
    return Page(data=[svc.read(t, staff=True) for t in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/tickets/{ticket_id}", response_model=StaffTicketDetail, summary="One request with the whole conversation and internal notes")
def ticket(ticket_id: str, db: DB, ctx: ReadDesk, meta: Meta) -> dict:
    svc = _staff(db, ctx, meta)
    t = svc.staff_get(ticket_id)
    if ctx.has("helpdesk:write"):
        svc.mark_read(t, staff=True)
    return _detail(svc, t, staff=True)


@router.post("/tickets/{ticket_id}/messages", response_model=StaffTicketDetail, summary="Answer the patient, or add an internal note")
@limiter.limit("60/minute")
def staff_reply(request: Request, response: Response, ticket_id: str, db: DB, ctx: WriteDesk, meta: Meta,
                body: Annotated[str, Form(max_length=5000)], internal: Annotated[bool, Form()] = False,
                next_status: Annotated[str | None, Form(pattern=r"^(resolved|closed)$")] = None,
                file: Annotated[UploadFile | None, File()] = None) -> dict:
    svc = _staff(db, ctx, meta)
    t = svc.staff_get(ticket_id)
    svc.staff_reply(t, body, internal=internal, file=_file(file), next_status=next_status or None)
    return _detail(svc, t, staff=True)


@router.patch("/tickets/{ticket_id}", response_model=StaffTicketDetail, summary="Change status, priority, category or who handles it")
def update(ticket_id: str, payload: TicketUpdate, db: DB, ctx: WriteDesk, meta: Meta) -> dict:
    svc = _staff(db, ctx, meta)
    t = svc.staff_update(svc.staff_get(ticket_id), status=payload.status, priority=payload.priority, assigned_to=payload.assigned_to,
                         unassign=payload.unassign, category=payload.category)
    return _detail(svc, t, staff=True)


@router.get("/tickets/{ticket_id}/messages/{message_id}/attachment", summary="An attachment (private; opening it is audit-logged)")
def attachment(ticket_id: str, message_id: str, db: DB, ctx: ReadDesk, meta: Meta):
    svc = _staff(db, ctx, meta)
    msg, handle = svc.open_attachment(svc.staff_get(ticket_id), message_id, staff=True)
    return _attachment_response(msg, handle)
