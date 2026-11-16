"""Calendar and video-meeting integrations.

* Google Calendar is connected per professional (each doctor's own calendar). Confirmed appointments become
  events (with a Google Meet link for online consultations); the doctor's other events block booking slots.
* Zoom is connected once per organization (Server-to-Server OAuth) and creates meetings for online consultations.
* Manual: a professional's fixed meeting link, or a link staff add to one appointment.

External calls never happen inside a booking request: appointment changes only mark
``appointment_external_events`` rows as pending, and the worker (``sync_external``) reconciles them with
retries. A provider outage can delay a calendar event, never a booking.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.connectors.google_app import clinic_client
from app.core.config import get_settings
from app.core.enums import AppointmentStatus, IntegrationStatus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow
from app.integrations import google_calendar as gcal
from app.integrations import zoom
from app.integrations.http import IntegrationAPIError
from app.integrations.ics import IcsEvent, calendar
from app.models import (
    Appointment,
    AppointmentExternalEvent,
    AppointmentReschedule,
    Branch,
    Customer,
    ExternalBusyBlock,
    Integration,
    IntegrationLog,
    Organization,
    Professional,
    Service,
    User,
)
from app.schemas.integration import (
    IntegrationLogRead,
    IntegrationRead,
    IntegrationsOverview,
    IntegrationUpdate,
    MeetingPreference,
    ProfessionalConnections,
    SyncIssue,
    ZoomConnect,
)
from app.security.crypto import decrypt_text, encrypt_text
from app.services.audit_service import RequestMeta, record_audit

log = get_logger(__name__)
GOOGLE = "google_calendar"
ZOOM = "zoom"
SYNCED_STATUSES = (AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN, AppointmentStatus.IN_PROGRESS, AppointmentStatus.COMPLETED)
MAX_ATTEMPTS = 8
GOOGLE_DEFAULTS = {"calendar_id": "primary", "create_meet": True, "block_busy": True, "show_patient_names": True}


def _creds(integ: Integration) -> dict[str, Any]:
    return json.loads(decrypt_text(integ.credentials_encrypted)) if integ.credentials_encrypted else {}


def _save_creds(integ: Integration, data: dict[str, Any]) -> None:
    integ.credentials_encrypted = encrypt_text(json.dumps(data))


def _log(db: Session, integ: Integration, action: str, status: str, *, error: str | None = None, started: float | None = None, request: dict | None = None) -> None:
    db.add(IntegrationLog(integration_id=integ.id, direction="outbound", action=action, status=status, request=request, error=error,
                          duration_ms=int((time.monotonic() - started) * 1000) if started else None, created_at=utcnow()))


class IntegrationService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None, *, can_manage_all: bool = False):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()
        self.can_manage_all = can_manage_all

    # -------------------------------------------------------------- access
    def professional(self, public_id: str) -> Professional:
        pro = self.db.scalar(select(Professional).where(Professional.public_id == public_id, Professional.organization_id == self.org.id, Professional.deleted_at.is_(None)))
        if pro is None:
            raise NotFoundError("Professional not found.")
        return pro

    def require_manage(self, pro: Professional | None) -> None:
        """Admins (integrations:write) manage everything; a professional manages only their own calendar and meeting link."""
        if self.can_manage_all:
            return
        if pro is not None and self.actor is not None and pro.user_id == self.actor.id:
            return
        raise PermissionDenied("You can only manage your own calendar connection.", code="permission_denied")

    def get(self, public_id: str) -> Integration:
        integ = self.db.scalar(select(Integration).where(Integration.public_id == public_id, Integration.organization_id == self.org.id))
        if integ is None:
            raise NotFoundError("Integration not found.")
        return integ

    def google_for(self, pro: Professional) -> Integration | None:
        return self.db.scalar(select(Integration).where(Integration.organization_id == self.org.id, Integration.provider == GOOGLE, Integration.professional_id == pro.id))

    def zoom_integration(self) -> Integration | None:
        return self.db.scalar(select(Integration).where(Integration.organization_id == self.org.id, Integration.provider == ZOOM, Integration.professional_id.is_(None)))

    # -------------------------------------------------------------- read
    def to_read(self, integ: Integration) -> IntegrationRead:
        pro = self.db.get(Professional, integ.professional_id) if integ.professional_id else None
        cfg = {k: v for k, v in (integ.config or {}).items() if k not in ("oauth_nonce_hash", "busy_pulled_at")}
        return IntegrationRead(id=integ.public_id, provider=integ.provider, name=integ.name, status=integ.status, is_enabled=integ.is_enabled, account=integ.external_account_id,
                               config=cfg, professional_id=pro.public_id if pro else None, professional_name=pro.display_name if pro else None,
                               connected_at=integ.connected_at, last_synced_at=integ.last_synced_at, last_error=integ.last_error)

    def meeting_pref(self, pro: Professional) -> MeetingPreference:
        return MeetingPreference.model_validate((pro.metadata_ or {}).get("meeting") or {})

    def effective_provider(self, pro: Professional) -> str:
        pref = self.meeting_pref(pro)
        google = self.google_for(pro)
        google_ok = google is not None and google.status == IntegrationStatus.CONNECTED and google.is_enabled and (google.config or {}).get("create_meet", True)
        zoom_integ = self.zoom_integration()
        zoom_ok = zoom_integ is not None and zoom_integ.status == IntegrationStatus.CONNECTED and zoom_integ.is_enabled
        if pref.provider == "auto":
            return "google_meet" if google_ok else "zoom" if zoom_ok else "manual" if pref.manual_url else "none"
        if pref.provider == "google_meet":
            return "google_meet" if google_ok else "none"
        if pref.provider == "zoom":
            return "zoom" if zoom_ok else "none"
        if pref.provider == "manual":
            return "manual" if pref.manual_url else "none"
        return "none"

    def feed_url(self, pro: Professional) -> str | None:
        token = (pro.metadata_ or {}).get("ical_token")
        return f"{get_settings().frontend_url.rstrip('/')}/api/v1/calendar-feeds/{token}.ics" if token else None

    def overview(self) -> IntegrationsOverview:
        pros = self.db.scalars(select(Professional).where(Professional.organization_id == self.org.id, Professional.deleted_at.is_(None), Professional.is_active.is_(True))
                               .order_by(Professional.sort_order, Professional.display_name)).all()
        if not self.can_manage_all:
            pros = [p for p in pros if self.actor is not None and p.user_id == self.actor.id]
        z = self.zoom_integration()
        return IntegrationsOverview(
            google_configured=clinic_client(self.db, self.org.id) is not None, google_redirect_uri=gcal.redirect_uri(), zoom=self.to_read(z) if z and self.can_manage_all else None,
            can_manage_all=self.can_manage_all,
            professionals=[ProfessionalConnections(
                professional_id=p.public_id, professional_name=p.display_name, is_me=bool(self.actor and p.user_id == self.actor.id),
                google=self.to_read(g) if (g := self.google_for(p)) else None, meeting=self.meeting_pref(p), effective_meeting_provider=self.effective_provider(p),
                feed_url=self.feed_url(p)) for p in pros],
        )

    def logs(self, integ: Integration, limit: int = 50) -> list[IntegrationLogRead]:
        rows = self.db.scalars(select(IntegrationLog).where(IntegrationLog.integration_id == integ.id).order_by(IntegrationLog.id.desc()).limit(limit)).all()
        return [IntegrationLogRead(action=r.action, status=r.status, error=r.error, duration_ms=r.duration_ms, created_at=r.created_at) for r in rows]

    # -------------------------------------------------------------- Google OAuth
    def google_start(self, pro: Professional, return_to: str) -> str:
        self.require_manage(pro)
        client = clinic_client(self.db, self.org.id)
        if client is None:
            raise ValidationFailed("Add your clinic's Google Cloud app first (Integrations → Google Cloud app).", code="google_not_configured")
        integ = self.google_for(pro)
        if integ is None:
            integ = Integration(organization_id=self.org.id, provider=GOOGLE, professional_id=pro.id, name=f"Google Calendar · {pro.display_name}",
                                status=IntegrationStatus.DISCONNECTED, is_enabled=False, config=dict(GOOGLE_DEFAULTS))
            self.db.add(integ)
            self.db.flush()
        nonce = secrets.token_urlsafe(24)
        integ.config = {**(integ.config or GOOGLE_DEFAULTS), "oauth_nonce_hash": hashlib.sha256(nonce.encode()).hexdigest()}
        s = get_settings()
        state = jwt.encode({"purpose": "google_calendar", "org": self.org.public_id, "integ": integ.public_id, "user": self.actor.public_id if self.actor else None,
                            "nonce": nonce, "return_to": return_to, "exp": int(time.time()) + 600}, s.secret_key, algorithm=s.jwt_algorithm)
        return gcal.authorization_url(state, client, login_hint=pro.email)

    @staticmethod
    def google_callback(db: Session, *, code: str | None, state: str, error: str | None) -> tuple[str, str]:
        """Completes the OAuth flow. Returns (return_to, outcome). The signed, single-use state replaces a session
        check because the browser arrives here as a top-level redirect from Google."""
        s = get_settings()
        try:
            claims = jwt.decode(state, s.secret_key, algorithms=[s.jwt_algorithm])
        except jwt.PyJWTError:
            return "/admin/integrations", "invalid_state"
        if claims.get("purpose") == "google_connector":  # Gmail, Contacts, Drive (Integration Hub) share this redirect URL
            from app.services.connector_service import google_connector_callback

            return google_connector_callback(db, code=code, state=state, error=error)
        if claims.get("purpose") != "google_calendar":
            return "/admin/integrations", "invalid_state"
        return_to = claims.get("return_to") or "/admin/integrations/calendar"
        org = db.scalar(select(Organization).where(Organization.public_id == claims.get("org")))
        integ = db.scalar(select(Integration).where(Integration.public_id == claims.get("integ"), Integration.organization_id == (org.id if org else -1)))
        if org is None or integ is None:
            return return_to, "invalid_state"
        expected = (integ.config or {}).get("oauth_nonce_hash")
        if not expected or not secrets.compare_digest(expected, hashlib.sha256(str(claims.get("nonce")).encode()).hexdigest()):
            return return_to, "invalid_state"  # already used or superseded by a newer attempt
        cfg = dict(integ.config or {})
        cfg.pop("oauth_nonce_hash", None)
        integ.config = cfg
        if error or not code:
            return return_to, "denied"
        started = time.monotonic()
        client = clinic_client(db, org.id)
        try:
            if client is None:
                raise IntegrationAPIError("The clinic's Google Cloud app is missing or switched off.")
            tokens = gcal.exchange_code(code, client)
            email = gcal.account_email(tokens["access_token"])
        except IntegrationAPIError as exc:
            integ.status, integ.last_error = IntegrationStatus.ERROR, str(exc)
            _log(db, integ, "oauth.connect", "failed", error=str(exc), started=started)
            return return_to, "failed"
        _save_creds(integ, {"refresh_token": tokens["refresh_token"], "access_token": tokens["access_token"], "expires_at": tokens["expires_at"],
                            "client_id": client.client_id})
        actor = db.scalar(select(User).where(User.public_id == claims.get("user"))) if claims.get("user") else None
        integ.status, integ.is_enabled, integ.last_error = IntegrationStatus.CONNECTED, True, None
        integ.external_account_id, integ.connected_at, integ.connected_by_user_id = email, utcnow(), actor.id if actor else None
        _log(db, integ, "oauth.connect", "ok", started=started)
        record_audit(db, action="integration.connected", actor=actor, organization_id=org.id, entity_type="integration", entity_id=integ.public_id,
                     after={"provider": GOOGLE, "account": email})
        db.flush()
        pull_busy(db, integ)
        return return_to, "connected"

    def update_google(self, integ: Integration, payload: IntegrationUpdate) -> Integration:
        pro = self.db.get(Professional, integ.professional_id) if integ.professional_id else None
        self.require_manage(pro)
        cfg = dict(integ.config or GOOGLE_DEFAULTS)
        for key in ("calendar_id", "create_meet", "block_busy", "show_patient_names"):
            value = getattr(payload, key)
            if value is not None:
                cfg[key] = value.strip() if isinstance(value, str) else value
        integ.config = cfg
        if payload.is_enabled is not None:
            integ.is_enabled = payload.is_enabled
        if not cfg.get("block_busy") or not integ.is_enabled:
            self.db.query(ExternalBusyBlock).filter(ExternalBusyBlock.integration_id == integ.id).delete()
        record_audit(self.db, action="integration.updated", actor=self.actor, organization_id=self.org.id, entity_type="integration", entity_id=integ.public_id, after=cfg, meta=self.meta)
        return integ

    def disconnect(self, integ: Integration) -> None:
        pro = self.db.get(Professional, integ.professional_id) if integ.professional_id else None
        self.require_manage(pro) if integ.provider == GOOGLE else self._require_admin()
        if integ.provider == GOOGLE and integ.credentials_encrypted:
            gcal.revoke(_creds(integ).get("refresh_token", ""))
        self.db.query(ExternalBusyBlock).filter(ExternalBusyBlock.integration_id == integ.id).delete()
        integ.credentials_encrypted, integ.status, integ.is_enabled, integ.last_error = None, IntegrationStatus.DISCONNECTED, False, None
        # Events already in the calendar stay there; we stop updating them.
        self.db.execute(update(AppointmentExternalEvent).where(AppointmentExternalEvent.integration_id == integ.id, AppointmentExternalEvent.status == "pending")
                        .values(status="deleted", last_error="integration disconnected"))
        record_audit(self.db, action="integration.disconnected", actor=self.actor, organization_id=self.org.id, entity_type="integration", entity_id=integ.public_id,
                     before={"provider": integ.provider, "account": integ.external_account_id}, meta=self.meta)

    def _require_admin(self) -> None:
        if not self.can_manage_all:
            raise PermissionDenied("Missing permission: integrations:write", code="permission_denied")

    # -------------------------------------------------------------- Zoom
    def connect_zoom(self, payload: ZoomConnect) -> Integration:
        self._require_admin()
        started = time.monotonic()
        try:
            token, expires = zoom.access_token(payload.account_id.strip(), payload.client_id.strip(), payload.client_secret.strip())
            me = zoom.ZoomClient(token).me(payload.default_user or "me")
        except IntegrationAPIError as exc:
            raise ValidationFailed(f"Zoom did not accept these credentials: {exc}", code="zoom_rejected") from exc
        integ = self.zoom_integration() or Integration(organization_id=self.org.id, provider=ZOOM, name="Zoom", status=IntegrationStatus.DISCONNECTED, is_enabled=False)
        if integ.id is None:
            self.db.add(integ)
        _save_creds(integ, {"account_id": payload.account_id.strip(), "client_id": payload.client_id.strip(), "client_secret": payload.client_secret.strip(),
                            "access_token": token, "expires_at": expires.isoformat()})
        integ.config = {"default_user": (payload.default_user or "").strip() or "me"}
        integ.status, integ.is_enabled, integ.last_error = IntegrationStatus.CONNECTED, True, None
        integ.external_account_id, integ.connected_at, integ.connected_by_user_id = me.get("email"), utcnow(), self.actor.id if self.actor else None
        self.db.flush()
        _log(self.db, integ, "connect", "ok", started=started)
        record_audit(self.db, action="integration.connected", actor=self.actor, organization_id=self.org.id, entity_type="integration", entity_id=integ.public_id,
                     after={"provider": ZOOM, "account": integ.external_account_id}, meta=self.meta)
        return integ

    def update(self, integ: Integration, payload: IntegrationUpdate) -> Integration:
        return self.update_google(integ, payload) if integ.provider == GOOGLE else self.update_zoom(integ, payload)

    def update_zoom(self, integ: Integration, payload: IntegrationUpdate) -> Integration:
        self._require_admin()
        if payload.default_user is not None:
            integ.config = {**(integ.config or {}), "default_user": payload.default_user.strip() or "me"}
        if payload.is_enabled is not None:
            integ.is_enabled = payload.is_enabled
        return integ

    def test(self, integ: Integration) -> Integration:
        pro = self.db.get(Professional, integ.professional_id) if integ.professional_id else None
        self.require_manage(pro) if integ.provider == GOOGLE else self._require_admin()
        started = time.monotonic()
        try:
            if integ.provider == GOOGLE:
                token = google_token(self.db, integ)
                gcal.CalendarClient(token, (integ.config or {}).get("calendar_id") or "primary").busy(utcnow(), utcnow() + timedelta(days=1))
            else:
                zoom.ZoomClient(zoom_token(self.db, integ)).me((integ.config or {}).get("default_user") or "me")
            integ.status, integ.last_error = IntegrationStatus.CONNECTED, None
            _log(self.db, integ, "test", "ok", started=started)
        except IntegrationAPIError as exc:
            integ.last_error = str(exc)
            if exc.reconnect:
                integ.status = IntegrationStatus.ERROR
            _log(self.db, integ, "test", "failed", error=str(exc), started=started)
        return integ

    # -------------------------------------------------------------- meeting + feeds
    def set_meeting(self, pro: Professional, pref: MeetingPreference) -> Professional:
        self.require_manage(pro)
        meta = dict(pro.metadata_ or {})
        meta["meeting"] = pref.model_dump()
        pro.metadata_ = meta
        record_audit(self.db, action="professional.meeting_settings", actor=self.actor, organization_id=self.org.id, entity_type="professional", entity_id=pro.public_id,
                     after=pref.model_dump(), meta=self.meta)
        return pro

    def rotate_feed(self, pro: Professional) -> str:
        self.require_manage(pro)
        meta = dict(pro.metadata_ or {})
        meta["ical_token"] = f"{pro.public_id}.{secrets.token_urlsafe(32)}"
        pro.metadata_ = meta
        record_audit(self.db, action="professional.calendar_feed_rotated", actor=self.actor, organization_id=self.org.id, entity_type="professional", entity_id=pro.public_id, meta=self.meta)
        return self.feed_url(pro) or ""

    def disable_feed(self, pro: Professional) -> None:
        self.require_manage(pro)
        meta = dict(pro.metadata_ or {})
        meta.pop("ical_token", None)
        pro.metadata_ = meta

    # -------------------------------------------------------------- sync issues
    def issues(self) -> list[SyncIssue]:
        rows = self.db.scalars(select(AppointmentExternalEvent).where(AppointmentExternalEvent.organization_id == self.org.id,
                                                                     or_(AppointmentExternalEvent.status == "failed", AppointmentExternalEvent.attempts > 1))
                               .order_by(AppointmentExternalEvent.updated_at.desc()).limit(100)).all()
        out = []
        for r in rows:
            appt = self.db.get(Appointment, r.appointment_id)
            pro = self.db.get(Professional, appt.professional_id) if appt else None
            if appt is None:
                continue
            out.append(SyncIssue(id=r.id, provider=r.provider, appointment_id=appt.public_id, appointment_reference=appt.reference, appointment_start_at=appt.start_at,
                                 professional_name=pro.display_name if pro else None, status=r.status, attempts=r.attempts, last_error=r.last_error, next_attempt_at=r.next_attempt_at))
        return out

    def retry_issue(self, issue_id: int) -> None:
        row = self.db.scalar(select(AppointmentExternalEvent).where(AppointmentExternalEvent.id == issue_id, AppointmentExternalEvent.organization_id == self.org.id))
        if row is None:
            raise NotFoundError("Sync item not found.")
        row.status, row.attempts, row.next_attempt_at, row.last_error = "pending", 0, utcnow(), None

    # -------------------------------------------------------------- appointment meeting link (manual)
    def set_appointment_link(self, appt: Appointment, link: str | None) -> Appointment:
        before = appt.meeting_link
        appt.meeting_link = link
        appt.meeting_provider = "manual" if link else None
        record_audit(self.db, action="appointment.meeting_link_set", actor=self.actor, organization_id=self.org.id, entity_type="appointment", entity_id=appt.reference,
                     before={"meeting_link": before}, after={"meeting_link": link}, meta=self.meta)
        if link and link != before and appt.status in SYNCED_STATUSES and appt.start_at > utcnow():
            from app.services.notification_service import NotificationService

            NotificationService(self.db, self.org, self.actor, self.meta).emit("appointment.meeting_link", appointment=appt)
        return appt


# ======================================================================== tokens
def google_token(db: Session, integ: Integration) -> str:
    """A valid access token for a Google connection of the clinic (refreshed with the clinic's own Google app)."""
    creds = _creds(integ)
    client = clinic_client(db, integ.organization_id)
    if client is None or (creds.get("client_id") and creds["client_id"] != client.client_id) or not creds.get("client_id"):
        integ.status = IntegrationStatus.ERROR
        integ.last_error = ("The clinic's Google Cloud app is missing or switched off (Integrations → Google Cloud app)." if client is None
                            else "This connection was made with a different Google app. Connect it again.")
        raise IntegrationAPIError(integ.last_error, reconnect=True)
    expires = datetime.fromisoformat(creds["expires_at"]) if creds.get("expires_at") else None
    if creds.get("access_token") and expires and expires > utcnow():
        return creds["access_token"]
    started = time.monotonic()
    try:
        fresh = gcal.refresh(creds.get("refresh_token", ""), client)
    except IntegrationAPIError as exc:
        _log(db, integ, "oauth.refresh", "failed", error=str(exc), started=started)
        if exc.reconnect:
            integ.status, integ.last_error = IntegrationStatus.ERROR, "Google access was revoked or expired. Reconnect the calendar."
        raise
    creds.update({"access_token": fresh["access_token"], "expires_at": fresh["expires_at"]})
    _save_creds(integ, creds)
    return fresh["access_token"]


def zoom_token(db: Session, integ: Integration) -> str:
    creds = _creds(integ)
    expires = datetime.fromisoformat(creds["expires_at"]) if creds.get("expires_at") else None
    if creds.get("access_token") and expires and expires > utcnow():
        return creds["access_token"]
    try:
        token, exp = zoom.access_token(creds["account_id"], creds["client_id"], creds["client_secret"])
    except IntegrationAPIError as exc:
        if exc.reconnect:
            integ.status, integ.last_error = IntegrationStatus.ERROR, "Zoom rejected the stored credentials. Connect Zoom again."
        raise
    creds.update({"access_token": token, "expires_at": exp.isoformat()})
    _save_creds(integ, creds)
    return token


# ======================================================================== marking
def mark_for_sync(db: Session, org: Organization, appt: Appointment) -> None:
    """Called on every appointment change. Applies a manual meeting link at once; queues external work."""
    pro = db.get(Professional, appt.professional_id)
    if pro is None:
        return
    svc = IntegrationService(db, org)
    provider = svc.effective_provider(pro) if appt.consultation_mode == "online" else "none"
    if provider == "manual" and appt.status in SYNCED_STATUSES and not appt.meeting_link:
        appt.meeting_link, appt.meeting_provider = svc.meeting_pref(pro).manual_url, "manual"
    targets: list[Integration] = []
    google = svc.google_for(pro)
    if google is not None and google.status == IntegrationStatus.CONNECTED and google.is_enabled:
        targets.append(google)
    z = svc.zoom_integration()
    if provider == "zoom" and z is not None:
        targets.append(z)
    existing = {r.integration_id: r for r in db.scalars(select(AppointmentExternalEvent).where(AppointmentExternalEvent.appointment_id == appt.id)).all()}
    now = utcnow()
    for integ in targets:
        row = existing.pop(integ.id, None)
        if row is None:
            if appt.status not in SYNCED_STATUSES:
                continue  # nothing to create yet
            row = AppointmentExternalEvent(organization_id=org.id, appointment_id=appt.id, integration_id=integ.id, provider=integ.provider)
            db.add(row)
        row.status, row.next_attempt_at, row.attempts = "pending", now, 0
    for row in existing.values():  # e.g. moved to another professional, or no longer online: remove what we created
        if row.external_id and row.status != "deleted":
            row.status, row.next_attempt_at, row.attempts = "pending", now, 0
    db.flush()


# ======================================================================== worker
def _desired(db: Session, row: AppointmentExternalEvent, appt: Appointment, integ: Integration) -> bool:
    if appt.status not in SYNCED_STATUSES or integ.status != IntegrationStatus.CONNECTED or not integ.is_enabled:
        return False
    if row.provider == GOOGLE:
        return integ.professional_id == appt.professional_id
    org = db.get(Organization, appt.organization_id)
    pro = db.get(Professional, appt.professional_id)
    return appt.consultation_mode == "online" and pro is not None and IntegrationService(db, org).effective_provider(pro) == "zoom"


def _event_body(db: Session, appt: Appointment, integ: Integration, with_meet: bool) -> dict[str, Any]:
    svc = db.get(Service, appt.service_id)
    cust = db.get(Customer, appt.customer_id)
    branch = db.get(Branch, appt.branch_id)
    show_names = (integ.config or {}).get("show_patient_names", True)
    who = (cust.full_name if show_names else f"{cust.full_name.split()[0][:1]}.") if cust else "Patient"
    lines = [f"Booking {appt.reference}", f"Status: {appt.status.replace('_', ' ')}"]
    if show_names and cust and cust.mobile:
        lines.append(f"Mobile: {cust.mobile}")
    if appt.meeting_link and appt.meeting_provider != "google_meet":
        lines.append(f"Video: {appt.meeting_link}")
    lines.append(f"{get_settings().frontend_url.rstrip('/')}/admin/appointments?ref={appt.reference}")
    body: dict[str, Any] = {
        "summary": f"{svc.name if svc else 'Appointment'} · {who}",
        "description": "\n".join(lines),
        "location": "Online" if appt.consultation_mode == "online" else (branch.name if branch else ""),
        "start": {"dateTime": appt.start_at.astimezone(UTC).isoformat(), "timeZone": appt.timezone},
        "end": {"dateTime": appt.end_at.astimezone(UTC).isoformat(), "timeZone": appt.timezone},
        "extendedProperties": {"private": {gcal.PRIVATE_KEY: appt.public_id}},
        "reminders": {"useDefault": True},
    }
    if with_meet:
        body["conferenceData"] = {"createRequest": {"requestId": f"apt-{appt.public_id}", "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    return body


def _sync_google(db: Session, row: AppointmentExternalEvent, appt: Appointment, integ: Integration, desired: bool) -> str | None:
    """Returns a newly created meeting link, if any."""
    client = gcal.CalendarClient(google_token(db, integ), (integ.config or {}).get("calendar_id") or "primary")
    if not desired:
        if row.external_id:
            client.delete(row.external_id)
            _log(db, integ, "event.delete", "ok", request={"appointment": appt.reference})
        row.status = "deleted"
        return None
    org = db.get(Organization, appt.organization_id)
    pro = db.get(Professional, appt.professional_id)
    wants_meet = appt.consultation_mode == "online" and IntegrationService(db, org).effective_provider(pro) == "google_meet" and not (appt.meeting_link and appt.meeting_provider != "google_meet")
    if row.external_id:
        event = client.patch(row.external_id, _event_body(db, appt, integ, wants_meet and not row.meeting_url), with_meet=wants_meet and not row.meeting_url)
        action = "event.update"
    else:
        event = client.insert(_event_body(db, appt, integ, wants_meet), with_meet=wants_meet)
        action = "event.create"
    _log(db, integ, action, "ok", request={"appointment": appt.reference})
    row.external_id, row.external_url, row.synced_start_at, row.status = event.get("id"), event.get("htmlLink"), appt.start_at, "synced"
    link = gcal.meet_link(event) if wants_meet else None
    if link and link != row.meeting_url:
        row.meeting_url = link
        return link
    return None


def _sync_zoom(db: Session, row: AppointmentExternalEvent, appt: Appointment, integ: Integration, desired: bool) -> str | None:
    client = zoom.ZoomClient(zoom_token(db, integ))
    if not desired:
        if row.external_id:
            client.delete(row.external_id)
            _log(db, integ, "meeting.delete", "ok", request={"appointment": appt.reference})
        row.status = "deleted"
        return None
    org = db.get(Organization, appt.organization_id)
    svc = db.get(Service, appt.service_id)
    pro = db.get(Professional, appt.professional_id)
    minutes = int((appt.end_at - appt.start_at).total_seconds() // 60)
    payload = zoom.meeting_payload(f"{org.name}: {svc.name if svc else 'Consultation'}", appt.start_at, minutes, appt.timezone, agenda=f"Booking {appt.reference}")
    if row.external_id:
        client.update(row.external_id, {k: payload[k] for k in ("topic", "start_time", "duration", "timezone")})
        _log(db, integ, "meeting.update", "ok", request={"appointment": appt.reference})
        row.synced_start_at, row.status = appt.start_at, "synced"
        return None
    host = IntegrationService(db, org).meeting_pref(pro).zoom_user or (integ.config or {}).get("default_user") or "me"
    meeting = client.create(host, payload)
    _log(db, integ, "meeting.create", "ok", request={"appointment": appt.reference, "host": host})
    row.external_id, row.external_url, row.meeting_url = str(meeting.get("id")), meeting.get("join_url"), meeting.get("join_url")
    row.synced_start_at, row.status = appt.start_at, "synced"
    return meeting.get("join_url")


def sync_external(db: Session, *, limit: int = 50, commit: bool = True) -> dict[str, int]:
    """Reconcile pending appointment ↔ calendar/meeting rows. Safe to run from several workers."""
    now = utcnow()
    db.execute(update(AppointmentExternalEvent).where(AppointmentExternalEvent.status == "syncing", AppointmentExternalEvent.updated_at < now - timedelta(minutes=15))
               .values(status="pending"))
    ids = db.scalars(select(AppointmentExternalEvent.id).where(AppointmentExternalEvent.status == "pending", or_(AppointmentExternalEvent.next_attempt_at.is_(None),
                                                                                                                 AppointmentExternalEvent.next_attempt_at <= now))
                     .order_by(AppointmentExternalEvent.next_attempt_at, AppointmentExternalEvent.id).limit(limit)).all()
    counts = {"synced": 0, "deleted": 0, "retry": 0, "failed": 0}
    for rid in ids:
        claimed = db.execute(update(AppointmentExternalEvent).where(AppointmentExternalEvent.id == rid, AppointmentExternalEvent.status == "pending")
                             .values(status="syncing", attempts=AppointmentExternalEvent.attempts + 1, updated_at=utcnow())).rowcount
        if not claimed:
            continue
        row = db.get(AppointmentExternalEvent, rid)
        db.refresh(row)
        appt = db.get(Appointment, row.appointment_id)
        integ = db.get(Integration, row.integration_id)
        try:
            desired = _desired(db, row, appt, integ)
            if not desired and integ.status != IntegrationStatus.CONNECTED and row.external_id:
                row.status, row.last_error = "deleted", "integration not connected; external item left as is"
                link = None
            else:
                link = (_sync_google if row.provider == GOOGLE else _sync_zoom)(db, row, appt, integ, desired)
            row.last_error, row.next_attempt_at = None, None
            integ.last_synced_at = utcnow()
            counts["synced" if row.status == "synced" else "deleted"] += 1
            if link and not (appt.meeting_link and appt.meeting_provider == "manual"):
                had = appt.meeting_link
                appt.meeting_link, appt.meeting_provider = link, ("google_meet" if row.provider == GOOGLE else "zoom")
                if link != had and appt.start_at > utcnow():
                    from app.services.notification_service import NotificationService

                    NotificationService(db, db.get(Organization, appt.organization_id)).emit("appointment.meeting_link", appointment=appt)
        except IntegrationAPIError as exc:
            row.last_error = str(exc)
            _log(db, integ, f"{row.provider}.sync", "failed", error=str(exc), request={"appointment": appt.reference})
            if exc.retryable and row.attempts < MAX_ATTEMPTS:
                row.status, row.next_attempt_at = "pending", utcnow() + timedelta(minutes=min(360, 2 ** row.attempts))
                counts["retry"] += 1
            else:
                row.status = "failed"
                counts["failed"] += 1
                if exc.reconnect:
                    integ.status, integ.last_error = IntegrationStatus.ERROR, integ.last_error or str(exc)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the others
            log.exception("integration.sync_crashed", row=rid)
            row.status, row.last_error, row.next_attempt_at = "pending", f"{type(exc).__name__}: {exc}", utcnow() + timedelta(minutes=10)
            counts["retry"] += 1
        if commit:
            db.commit()
        else:
            db.flush()
    return counts


def pull_busy(db: Session, integ: Integration) -> int:
    """Replace the busy blocks imported from one professional's Google Calendar."""
    if integ.provider != GOOGLE or integ.status != IntegrationStatus.CONNECTED or not integ.is_enabled or not (integ.config or {}).get("block_busy", True):
        return 0
    now = utcnow()
    started = time.monotonic()
    try:
        client = gcal.CalendarClient(google_token(db, integ), (integ.config or {}).get("calendar_id") or "primary")
        busy = client.busy(now - timedelta(hours=1), now + timedelta(days=get_settings().calendar_sync_days_ahead))
    except IntegrationAPIError as exc:
        integ.last_error = str(exc)
        _log(db, integ, "busy.pull", "failed", error=str(exc), started=started)
        return 0
    db.query(ExternalBusyBlock).filter(ExternalBusyBlock.integration_id == integ.id).delete()
    for start, end in busy:
        db.add(ExternalBusyBlock(organization_id=integ.organization_id, professional_id=integ.professional_id, integration_id=integ.id, start_at=start, end_at=end,
                                 title="Busy", fetched_at=now))
    integ.last_synced_at, integ.last_error = now, None
    _log(db, integ, "busy.pull", "ok", started=started, request={"blocks": len(busy)})
    db.flush()
    return len(busy)


def pull_all_busy(db: Session, *, commit: bool = True, every_minutes: int = 10) -> int:
    """Refresh imported busy time, at most every ``every_minutes`` per calendar."""
    total = 0
    cutoff = (utcnow() - timedelta(minutes=every_minutes)).isoformat()
    for integ in db.scalars(select(Integration).where(Integration.provider == GOOGLE, Integration.status == IntegrationStatus.CONNECTED, Integration.is_enabled.is_(True))).all():
        if (integ.config or {}).get("busy_pulled_at", "") > cutoff:
            continue
        integ.config = {**(integ.config or {}), "busy_pulled_at": utcnow().isoformat()}
        total += pull_busy(db, integ)
        if commit:
            db.commit()
    return total


# ======================================================================== iCalendar
def appointment_ics_event(db: Session, appt: Appointment, *, for_staff: bool) -> IcsEvent:
    org = db.get(Organization, appt.organization_id)
    svc = db.get(Service, appt.service_id)
    pro = db.get(Professional, appt.professional_id)
    branch = db.get(Branch, appt.branch_id)
    cust = db.get(Customer, appt.customer_id)
    seq = db.query(AppointmentReschedule).filter(AppointmentReschedule.appointment_id == appt.id).count()
    from app.services.notification_service import _address

    online = appt.consultation_mode == "online"
    if for_staff:
        summary = f"{svc.name if svc else 'Appointment'} · {cust.full_name if cust else ''}".strip(" ·")
    else:
        summary = f"{svc.name if svc else 'Appointment'} with {pro.display_name if pro else org.name}"
    desc = [f"Booking {appt.reference} at {org.name}"]
    if online and appt.meeting_link:
        desc.append(f"Join online: {appt.meeting_link}")
    if not for_staff and org.phone:
        desc.append(f"Questions? {org.phone}")
    location = (appt.meeting_link or "Online") if online else ", ".join(x for x in [branch.name if branch else "", _address(branch.address) if branch else ""] if x)
    status = "CANCELLED" if appt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.EXPIRED) else ("CONFIRMED" if appt.status in SYNCED_STATUSES else "TENTATIVE")
    domain = get_settings().frontend_url.split("//")[-1].split("/")[0].split(":")[0] or "appointments"
    return IcsEvent(uid=f"{appt.public_id}@{domain}", start=appt.start_at, end=appt.end_at, summary=summary, description="\n".join(desc), location=location,
                    url=appt.meeting_link if online and appt.meeting_link else None, status=status, sequence=seq, updated=appt.updated_at)


def appointment_ics(db: Session, appt: Appointment, *, for_staff: bool = False) -> str:
    org = db.get(Organization, appt.organization_id)
    return calendar([appointment_ics_event(db, appt, for_staff=for_staff)], name=org.name)


def professional_feed(db: Session, token: str) -> str | None:
    pro_id, _, secret = token.partition(".")
    if not pro_id or len(secret) < 20:
        return None
    pro = db.scalar(select(Professional).where(Professional.public_id == pro_id, Professional.deleted_at.is_(None)))
    stored = ((pro.metadata_ or {}).get("ical_token") if pro else None) or ""
    if pro is None or not secrets.compare_digest(stored, token):
        return None
    now = utcnow()
    appts = db.scalars(select(Appointment).where(Appointment.professional_id == pro.id, Appointment.start_at >= now - timedelta(days=30),
                                                 Appointment.start_at <= now + timedelta(days=180),
                                                 Appointment.status.in_([*SYNCED_STATUSES, AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION, AppointmentStatus.CANCELLED]))
                       .order_by(Appointment.start_at)).all()
    return calendar([appointment_ics_event(db, a, for_staff=True) for a in appts], name=f"{pro.display_name} · appointments", method=None)
