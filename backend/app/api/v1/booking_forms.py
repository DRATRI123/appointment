"""Booking form builder (staff)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.schemas.booking_form import BookingFormCreate, BookingFormRead, BookingFormUpdate, FormResponseRead
from app.schemas.common import APIModel, Message
from app.services.appointment_service import AppointmentService
from app.services.form_service import FormService

router = APIRouter(prefix="/booking-forms", tags=["booking-forms"])
ReadForms = Annotated[TenantContext, Depends(require_permission("booking_forms:read"))]
WriteForms = Annotated[TenantContext, Depends(require_permission("booking_forms:write"))]


class AssignRequest(APIModel):
    service_id: str
    form_id: str | None = None


@router.get("", response_model=list[BookingFormRead])
def list_forms(db: DB, ctx: ReadForms, meta: Meta, include_templates: bool = True, all_versions: bool = False):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    return [svc.to_read(f) for f in svc.list(include_templates=include_templates, latest_only=not all_versions)]


@router.get("/templates", response_model=list[dict], summary="Built-in starting points")
def templates(db: DB, ctx: ReadForms, meta: Meta):
    return FormService(db, ctx.organization, ctx.user, meta).templates()


@router.post("", response_model=BookingFormRead, status_code=status.HTTP_201_CREATED)
def create_form(payload: BookingFormCreate, db: DB, ctx: WriteForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.create(payload))


@router.get("/{form_id}", response_model=BookingFormRead)
def get_form(form_id: str, db: DB, ctx: ReadForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.get(form_id))


@router.patch("/{form_id}", response_model=BookingFormRead, summary="Edit a form (editing fields of a published form creates a new draft version)")
def update_form(form_id: str, payload: BookingFormUpdate, db: DB, ctx: WriteForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.update(svc.get(form_id), payload))


@router.post("/{form_id}/publish", response_model=BookingFormRead)
def publish_form(form_id: str, db: DB, ctx: WriteForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    return svc.to_read(svc.publish(svc.get(form_id)))


@router.delete("/{form_id}", response_model=Message)
def delete_form(form_id: str, db: DB, ctx: WriteForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    svc.delete(svc.get(form_id))
    return Message(detail="Form deleted.")


@router.post("/assign", response_model=Message, summary="Attach a form to a service (form_id null detaches)")
def assign(payload: AssignRequest, db: DB, ctx: WriteForms, meta: Meta):
    svc = FormService(db, ctx.organization, ctx.user, meta)
    form = svc.get(payload.form_id) if payload.form_id else None
    service = svc.assign_to_service(form, payload.service_id)
    return Message(detail=f"{service.name} now uses {form.name if form else 'no booking form'}.")


@router.get("/responses/by-appointment/{appointment_id}", response_model=FormResponseRead | None)
def response_for_appointment(appointment_id: str, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("appointments:read"))], meta: Meta):
    appt = AppointmentService(db, ctx.organization, ctx.user, meta).get(appointment_id)
    return FormService(db, ctx.organization, ctx.user, meta).response_for_appointment(appt)
