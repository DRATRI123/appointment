"""Incoming automation actions from n8n: POST /api/v1/automation/n8n/{integration id}.

Checks, in order: the integration exists and is switched on; ``X-Webhook-Signature`` (``t=<unix>,v1=<HMAC-SHA256 of
"<t>.<raw body>">`` with the incoming secret) is valid and less than 5 minutes old; ``X-Request-Id`` was never used
before (replay protection, kept 7 days); the action is one the clinic allowed. Then the action runs through the same
services as a staff action, so booking rules, payment verification and permissions are never bypassed: n8n cannot book,
confirm, cancel or verify anything.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.connectors.n8n import parse_list
from app.connectors.registry import CONNECTORS
from app.core.time import utcnow
from app.models import Appointment, AutomationRequest, Customer, FollowUpTask, Integration, Organization
from app.security.crypto import decrypt_text
from app.services.audit_service import record_audit
from app.webhooks.catalog import appointment_data
from app.webhooks.security import verify

TOLERANCE_SECONDS = 300
REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")
NOTIFY_EVENTS = ("appointment.confirmed", "appointment.reminder", "appointment.meeting_link", "appointment.pending_payment")


class Refused(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _appointment(db, org: Organization, data: dict) -> Appointment:
    ref = str(data.get("appointment_id") or data.get("reference") or "")
    appt = db.scalar(select(Appointment).where(Appointment.organization_id == org.id, (Appointment.public_id == ref) | (Appointment.reference == ref)))
    if appt is None:
        raise Refused(404, "appointment_not_found", "No appointment with this id or reference in this clinic.")
    return appt


def _customer(db, org: Organization, customer_id: Any) -> Customer | None:
    if not customer_id:
        return None
    c = db.scalar(select(Customer).where(Customer.organization_id == org.id, Customer.public_id == str(customer_id), Customer.deleted_at.is_(None)))
    if c is None:
        raise Refused(404, "customer_not_found", "No patient with this id in this clinic.")
    return c


def run_action(db, org: Organization, integ: Integration, action: str, data: dict) -> dict[str, Any]:
    from app.services.notification_service import NotificationService

    if action == "get_appointment":
        return {"appointment": appointment_data(db, _appointment(db, org, data))}
    if action == "create_follow_up":
        title = str(data.get("title") or "").strip()
        if not 2 <= len(title) <= 200:
            raise Refused(422, "invalid_title", "title must be 2–200 characters.")
        due = None
        if data.get("due_at"):
            try:
                due = datetime.fromisoformat(str(data["due_at"]).replace("Z", "+00:00"))
            except ValueError as exc:
                raise Refused(422, "invalid_due_at", "due_at must be an ISO 8601 date-time.") from exc
        appt = _appointment(db, org, data) if (data.get("appointment_id") or data.get("reference")) else None
        cust = _customer(db, org, data.get("customer_id")) or (db.get(Customer, appt.customer_id) if appt else None)
        task = FollowUpTask(organization_id=org.id, customer_id=cust.id if cust else None, appointment_id=appt.id if appt else None, title=title,
                            details=(str(data.get("details") or "")[:1000] or None), due_at=due, source="n8n", integration_id=integ.id)
        db.add(task)
        db.flush()
        return {"task": {"id": task.public_id, "title": task.title, "due_at": due.isoformat() if due else None}}
    if action in ("send_notification", "trigger_reminder"):
        appt = _appointment(db, org, data)
        event = "appointment.reminder" if action == "trigger_reminder" else str(data.get("event") or "")
        if event not in NOTIFY_EVENTS:
            raise Refused(422, "event_not_allowed", f"event must be one of: {', '.join(NOTIFY_EVENTS)}.")
        if appt.start_at <= utcnow() and event == "appointment.reminder":
            raise Refused(409, "appointment_started", "The appointment has already started.")
        hours = max(1, round((appt.start_at - utcnow()).total_seconds() / 3600))
        made = NotificationService(db, org).emit(event, appointment=appt, extra={"hours_before": str(hours)},
                                                 dedupe=f"n8n:{event}:{appt.id}:{utcnow().strftime('%Y%m%d%H')}")
        return {"queued": len(made)}
    if action == "update_customer":
        from app.schemas.customer import CustomerUpdate
        from app.services.customer_management_service import CustomerManagementService

        cust = _customer(db, org, data.get("customer_id"))
        if cust is None:
            raise Refused(422, "customer_required", "customer_id is required.")
        allowed: dict[str, Any] = {}
        if "tags" in data:
            if not isinstance(data["tags"], list) or len(data["tags"]) > 30 or not all(isinstance(t, str) and len(t) <= 40 for t in data["tags"]):
                raise Refused(422, "invalid_tags", "tags must be a list of up to 30 short texts.")
            allowed["tags"] = data["tags"]
        if "communication_preferences" in data:
            prefs = data["communication_preferences"]
            if not isinstance(prefs, dict) or not set(prefs) <= {"sms", "whatsapp", "email"} or not all(isinstance(v, bool) for v in prefs.values()):
                raise Refused(422, "invalid_preferences", "communication_preferences may set sms, whatsapp and email to true or false.")
            allowed["communication_preferences"] = {**(cust.communication_preferences or {}), **prefs}
        if not allowed:
            raise Refused(422, "nothing_to_update", "Only tags and communication_preferences can be changed by automations.")
        CustomerManagementService(db, org, None).update(cust, CustomerUpdate(**allowed))
        return {"customer": {"id": cust.public_id, "tags": cust.tags or [], "communication_preferences": cust.communication_preferences}}
    raise Refused(422, "unknown_action", "Unknown action.")


def handle(db, integration_id: str, headers, body: bytes) -> tuple[int, dict[str, Any]]:
    integ = db.scalar(select(Integration).where(Integration.public_id == integration_id, Integration.provider == "n8n"))
    if integ is None or not integ.is_enabled or not integ.credentials_encrypted:
        return 404, {"code": "not_found", "detail": "Unknown or switched-off automation."}
    secret = json.loads(decrypt_text(integ.credentials_encrypted)).get("incoming_secret")
    signature = headers.get("x-webhook-signature") or ""
    if not secret or not verify(secret, signature, body, now=int(time.time()), tolerance=TOLERANCE_SECONDS):
        return 401, {"code": "bad_signature", "detail": "Signature missing, wrong or older than 5 minutes."}
    request_id = headers.get("x-request-id") or ""
    if not REQUEST_ID.match(request_id):
        return 400, {"code": "request_id_required", "detail": "Send a unique X-Request-Id (8–80 letters, digits, - _ . :)."}
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return 400, {"code": "invalid_json", "detail": "The body must be JSON: {\"action\": \"…\", \"data\": {…}}."}
    action, data = str(payload.get("action") or ""), payload.get("data") or {}
    if not isinstance(data, dict):
        return 400, {"code": "invalid_json", "detail": "data must be an object."}
    org = db.get(Organization, integ.organization_id)
    log = AutomationRequest(organization_id=integ.organization_id, integration_id=integ.id, request_id=request_id, action=action[:48] or "-", status="ok", received_at=utcnow())
    try:
        with db.begin_nested():
            db.add(log)
            db.flush()
    except IntegrityError:
        return 409, {"code": "replayed", "detail": "This X-Request-Id was already used."}
    allowed = set(parse_list({**CONNECTORS["n8n"].defaults, **(integ.config or {})}.get("allowed_actions")))
    try:
        if action not in allowed:
            raise Refused(403, "action_not_allowed", f"The clinic has not allowed “{action}” for automations.")
        with db.begin_nested():
            result = run_action(db, org, integ, action, data)
    except Refused as exc:
        log.status, log.detail = "refused", exc.message[:300]
        return exc.status, {"code": exc.code, "detail": exc.message}
    record_audit(db, action=f"automation.{action}", actor=None, organization_id=org.id, entity_type="integration", entity_id=integ.public_id,
                 after={"request_id": request_id}, purpose="n8n automation")
    db.execute(delete(AutomationRequest).where(AutomationRequest.integration_id == integ.id, AutomationRequest.received_at < utcnow() - timedelta(days=7)))
    return 200, {"ok": True, "request_id": request_id, **result}
