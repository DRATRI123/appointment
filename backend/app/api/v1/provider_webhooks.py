"""Callbacks from message providers.

WhatsApp (Meta Cloud API): Meta → App → WhatsApp → Configuration → Callback URL ``<site>/api/v1/webhooks/whatsapp``
with the verify token from Super admin → Integrations → WhatsApp; subscribe to the "messages" field.
* GET answers Meta's verification challenge.
* POST is accepted only with a valid ``X-Hub-Signature-256`` (HMAC-SHA256 of the raw body with the app secret). It records
  delivery reports (sent, delivered, read, failed) against our messages and honours opt-out: a reply of STOP turns
  WhatsApp off for that number; START turns it back on (recorded as the person's own request).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select

from app.api.deps import DB
from app.core.time import utcnow
from app.models import Customer, Notification, NotificationLog
from app.security.rate_limit import limiter
from app.services.audit_service import record_audit
from app.services.platform_config import runtime_settings

router = APIRouter(prefix="/webhooks", tags=["provider-webhooks"])
STOP_WORDS = {"STOP", "UNSUBSCRIBE", "STOP ALL", "CANCEL", "OPT OUT", "OPTOUT"}
START_WORDS = {"START", "SUBSCRIBE", "OPT IN", "OPTIN"}


@router.get("/whatsapp", response_class=PlainTextResponse, include_in_schema=False)
def whatsapp_verify(mode: str = Query(default="", alias="hub.mode"), token: str = Query(default="", alias="hub.verify_token"),
                    challenge: str = Query(default="", alias="hub.challenge")) -> PlainTextResponse:
    expected = runtime_settings().whatsapp_webhook_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected) and challenge.isdigit():
        return PlainTextResponse(challenge)
    return PlainTextResponse("forbidden", status_code=403)


def _apply_status(db, st: dict) -> bool:
    mid, status = st.get("id"), st.get("status")
    if not mid or status not in ("sent", "delivered", "read", "failed"):
        return False
    log = db.scalar(select(NotificationLog).where(NotificationLog.provider_message_id == mid).order_by(NotificationLog.id.desc()))
    if log is None:
        return False
    n = db.get(Notification, log.notification_id)
    when = datetime.fromtimestamp(int(st.get("timestamp") or 0), UTC) if str(st.get("timestamp") or "").isdigit() else utcnow()
    error = None
    if status == "failed":
        errs = st.get("errors") or [{}]
        error = f"WhatsApp: {errs[0].get('title') or errs[0].get('message') or 'failed'} ({errs[0].get('code')})"[:500]
    db.add(NotificationLog(notification_id=log.notification_id, provider="meta", provider_message_id=mid, status=status, error=error, created_at=when))
    if n is not None:
        if status == "read" and n.read_at is None:
            n.read_at = when
        if status == "failed":
            n.status, n.last_error = "failed", error
    return True


def _apply_reply(db, msg: dict) -> int:
    text = ((msg.get("text") or {}).get("body") or (msg.get("button") or {}).get("text") or "").strip().upper()
    wa = str(msg.get("from") or "")
    if not wa.isdigit() or text not in STOP_WORDS | START_WORDS:
        return 0
    changed = 0
    for c in db.scalars(select(Customer).where(Customer.mobile == f"+{wa}", Customer.deleted_at.is_(None))).all():
        prefs = dict(c.communication_preferences or {})
        on = text in START_WORDS
        if bool(prefs.get("whatsapp")) == on:
            continue
        prefs["whatsapp"] = on
        prefs[f"whatsapp_{'opt_in' if on else 'opt_out'}_at"] = utcnow().isoformat()
        prefs[f"whatsapp_{'opt_in' if on else 'opt_out'}_source"] = "whatsapp_reply"
        c.communication_preferences = prefs
        record_audit(db, action="customer.whatsapp_opt_in" if on else "customer.whatsapp_opt_out", actor=None, organization_id=c.organization_id,
                     entity_type="customer", entity_id=c.public_id, purpose="reply on WhatsApp")
        changed += 1
    return changed


async def raw_body(request: Request) -> bytes:
    return await request.body()


@router.post("/whatsapp", include_in_schema=False)
@limiter.limit("300/minute")
def whatsapp_events(request: Request, db: DB, body: Annotated[bytes, Depends(raw_body)]) -> JSONResponse:
    secret = runtime_settings().whatsapp_app_secret
    given = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(given, expected):
        return JSONResponse({"code": "bad_signature"}, status_code=401)
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"code": "invalid_json"}, status_code=400)

    def work() -> dict[str, int]:
        counts = {"statuses": 0, "opt_changes": 0}
        for entry in data.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for st in value.get("statuses") or []:
                    counts["statuses"] += _apply_status(db, st)
                for msg in value.get("messages") or []:
                    counts["opt_changes"] += _apply_reply(db, msg)
        return counts

    counts = work()
    return JSONResponse({"ok": True, **counts})  # 200 quickly: Meta retries anything else
