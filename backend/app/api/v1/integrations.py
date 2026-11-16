"""Calendar and video-meeting integrations, appointment meeting links and iCalendar downloads/feeds."""
from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Meta, OptionalUser, TenantContext, get_tenant_context
from app.core.config import get_settings
from app.core.database import writes_on_read
from app.core.exceptions import NotFoundError, PermissionDenied
from app.models import Appointment, Customer, Professional
from app.schemas.common import Message
from app.schemas.integration import (
    AuthorizationURL,
    GoogleConnect,
    IntegrationLogRead,
    IntegrationRead,
    IntegrationsOverview,
    IntegrationUpdate,
    MeetingLinkUpdate,
    MeetingPreference,
    SyncIssue,
    ZoomConnect,
)
from app.services.integration_service import IntegrationService, appointment_ics, professional_feed, pull_busy

router = APIRouter(prefix="/integrations", tags=["integrations"])
appointments_router = APIRouter(tags=["integrations"])
feeds_router = APIRouter(tags=["calendar-feeds"])
Tenant = Annotated[TenantContext, Depends(get_tenant_context)]
ICS = "text/calendar; charset=utf-8"


def _svc(db, ctx: TenantContext, meta) -> IntegrationService:
    return IntegrationService(db, ctx.organization, ctx.user, meta, can_manage_all=ctx.has("integrations:write"))


def _require_view(db, ctx: TenantContext) -> None:
    """Admins see everything; a professional linked to this account sees their own connections."""
    if ctx.has("integrations:read") or ctx.has("integrations:write"):
        return
    own = db.scalar(select(Professional.id).where(Professional.organization_id == ctx.organization.id, Professional.user_id == ctx.user.id))
    if own is None:
        raise PermissionDenied("Missing permission: integrations:read", code="permission_denied")


@router.get("", response_model=IntegrationsOverview)
def overview(db: DB, ctx: Tenant, meta: Meta):
    _require_view(db, ctx)
    svc = _svc(db, ctx, meta)
    if not ctx.has("integrations:read") and not ctx.has("integrations:write"):
        svc.can_manage_all = False
    return svc.overview()


@router.post("/google/connect", response_model=AuthorizationURL, summary="Start connecting a professional's Google Calendar")
def google_connect(payload: GoogleConnect, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return AuthorizationURL(authorization_url=svc.google_start(svc.professional(payload.professional_id), payload.return_to))


@router.get("/google/callback", include_in_schema=False)
@writes_on_read  # access is audit-logged
def google_callback(db: DB, state: str = "", code: str | None = None, error: str | None = None):
    return_to, outcome = IntegrationService.google_callback(db, code=code, state=state, error=error)
    db.commit()
    return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}{return_to}?{urlencode({'google': outcome})}", status_code=303)


@router.get("/sync-issues", response_model=list[SyncIssue])
def sync_issues(db: DB, ctx: Tenant, meta: Meta):
    ctx.require("integrations:read")
    return _svc(db, ctx, meta).issues()


@router.post("/sync-issues/{issue_id}/retry", response_model=Message)
def retry_issue(issue_id: int, db: DB, ctx: Tenant, meta: Meta):
    ctx.require("integrations:write")
    _svc(db, ctx, meta).retry_issue(issue_id)
    return Message(detail="Queued for another attempt.")


@router.post("/zoom", response_model=IntegrationRead, summary="Connect Zoom with Server-to-Server OAuth credentials (tested before saving)")
def connect_zoom(payload: ZoomConnect, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.connect_zoom(payload))


@router.get("/professionals/{professional_id}/meeting", response_model=MeetingPreference)
def get_meeting(professional_id: str, db: DB, ctx: Tenant, meta: Meta):
    _require_view(db, ctx)
    svc = _svc(db, ctx, meta)
    return svc.meeting_pref(svc.professional(professional_id))


@router.put("/professionals/{professional_id}/meeting", response_model=MeetingPreference, summary="How online consultations get their video link")
def put_meeting(professional_id: str, payload: MeetingPreference, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.meeting_pref(svc.set_meeting(svc.professional(professional_id), payload))


@router.post("/professionals/{professional_id}/feed", response_model=Message, summary="Create or replace the private calendar feed URL")
def rotate_feed(professional_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return Message(detail=svc.rotate_feed(svc.professional(professional_id)))


@router.delete("/professionals/{professional_id}/feed", response_model=Message)
def disable_feed(professional_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.disable_feed(svc.professional(professional_id))
    return Message(detail="Calendar feed turned off.")


@router.patch("/{integration_id}", response_model=IntegrationRead)
def update_integration(integration_id: str, payload: IntegrationUpdate, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.update(svc.get(integration_id), payload))


@router.post("/{integration_id}/test", response_model=IntegrationRead)
def test_integration(integration_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.to_read(svc.test(svc.get(integration_id)))


@router.post("/{integration_id}/sync", response_model=IntegrationRead, summary="Re-read busy time from the calendar now")
def sync_now(integration_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    integ = svc.get(integration_id)
    svc.require_manage(db.get(Professional, integ.professional_id) if integ.professional_id else None)
    pull_busy(db, integ)
    return svc.to_read(integ)


@router.get("/{integration_id}/calendars", summary="Google calendars this doctor can add bookings to")
def list_calendars(integration_id: str, db: DB, ctx: Tenant, meta: Meta) -> list[dict]:
    from app.integrations import google_calendar as gcal
    from app.integrations.http import IntegrationAPIError
    from app.services.integration_service import google_token

    _require_view(db, ctx)
    svc = _svc(db, ctx, meta)
    integ = svc.get(integration_id)
    if integ.provider != "google_calendar":
        from app.core.exceptions import ValidationFailed

        raise ValidationFailed("This is not a Google Calendar connection.", code="not_google_calendar")
    svc.require_manage(db.get(Professional, integ.professional_id) if integ.professional_id else None)
    try:
        return gcal.list_calendars(google_token(db, integ))
    except IntegrationAPIError as exc:
        if exc.status == 403:
            raise PermissionDenied("Connect Google again to choose a calendar (this connection was made before calendar choice existed).",
                                   code="reconnect_for_calendars") from exc
        raise


@router.get("/{integration_id}/logs", response_model=list[IntegrationLogRead])
def integration_logs(integration_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    integ = svc.get(integration_id)
    svc.require_manage(db.get(Professional, integ.professional_id) if integ.professional_id else None)
    return svc.logs(integ)


@router.delete("/{integration_id}", response_model=Message)
def disconnect(integration_id: str, db: DB, ctx: Tenant, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.disconnect(svc.get(integration_id))
    return Message(detail="Disconnected.")


# ------------------------------------------------------------------ appointments
def _staff_appointment(db, ctx: TenantContext, appointment_id: str) -> Appointment:
    appt = db.scalar(select(Appointment).where(Appointment.public_id == appointment_id, Appointment.organization_id == ctx.organization.id))
    if appt is None:
        raise NotFoundError("Appointment not found.")
    if not ctx.has("appointments:read"):
        pro = db.get(Professional, appt.professional_id)
        if not (ctx.has("appointments:read_own") and pro is not None and pro.user_id == ctx.user.id):
            raise PermissionDenied("Missing permission: appointments:read", code="permission_denied")
    return appt


@appointments_router.put("/appointments/{appointment_id}/meeting", response_model=Message, summary="Set or clear the video link of one appointment")
def set_meeting_link(appointment_id: str, payload: MeetingLinkUpdate, db: DB, ctx: Tenant, meta: Meta):
    ctx.require("appointments:write")
    appt = _staff_appointment(db, ctx, appointment_id)
    IntegrationService(db, ctx.organization, ctx.user, meta).set_appointment_link(appt, payload.meeting_link)
    return Message(detail="Meeting link saved." if payload.meeting_link else "Meeting link removed.")


@appointments_router.get("/appointments/{appointment_id}/calendar.ics", summary="Appointment as an iCalendar file (staff)")
def staff_ics(appointment_id: str, db: DB, ctx: Tenant):
    appt = _staff_appointment(db, ctx, appointment_id)
    return Response(appointment_ics(db, appt, for_staff=True), media_type=ICS, headers={"Content-Disposition": f'attachment; filename="{appt.reference}.ics"'})


@appointments_router.get("/customer/appointments/{appointment_id}/calendar.ics", summary="Add to calendar (signed-in customer)")
def customer_ics(appointment_id: str, db: DB, user: CurrentUser):
    appt = db.scalar(select(Appointment).join(Customer, Customer.id == Appointment.customer_id).where(Appointment.public_id == appointment_id, Customer.user_id == user.id))
    if appt is None:
        raise NotFoundError("Appointment not found.")
    return Response(appointment_ics(db, appt), media_type=ICS, headers={"Content-Disposition": f'attachment; filename="{appt.reference}.ics"'})


@appointments_router.get("/public/organizations/{slug}/appointments/{reference}/calendar.ics", summary="Add to calendar (access token)")
def public_ics(slug: str, reference: str, db: DB, user: OptionalUser, access_token: str | None = None):
    from app.services.appointment_service import AppointmentService
    from app.services.organization_service import OrganizationService

    org = OrganizationService(db).get_by_slug_public(slug)
    appt = AppointmentService(db, org, user).get_by_reference(reference, access_token, user)
    return Response(appointment_ics(db, appt), media_type=ICS, headers={"Content-Disposition": f'attachment; filename="{appt.reference}.ics"'})


# ------------------------------------------------------------------ private feeds
@feeds_router.get("/calendar-feeds/{token}.ics", summary="A professional's private calendar feed (subscribe from any calendar app)")
def feed(token: str, db: DB):
    body = professional_feed(db, token)
    if body is None:
        raise NotFoundError("Calendar feed not found.")
    return Response(body, media_type=ICS, headers={"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex"})

