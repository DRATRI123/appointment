"""Privacy policy per clinic: masking, reveal, re-authentication, screen lock, watermark, print, export limits and
bulk-access detection. Settings live in the existing ``privacy`` settings section (Admin → Settings → Privacy).

Everything here is enforced by the API. The website only reflects it (masked values, lock screen, watermark), because
anything sent to a browser can be read by whoever controls that browser.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import PermissionDenied, RateLimited, ValidationFailed
from app.core.observability import security_event
from app.core.time import utcnow
from app.models import AuditLog, Organization

ROLE_CODES = ("org_owner", "org_admin", "branch_manager", "doctor", "professional", "receptionist", "accountant", "staff")

# (default, minimum, maximum) for numbers
LIMITS: dict[str, tuple[float, float, float]] = {
    "reauth_window_minutes": (10, 1, 120),
    "lock_after_minutes": (15, 1, 240),
    "watermark_opacity": (0.08, 0.03, 0.3),
    "max_exports_per_day": (20, 1, 500),
    "max_export_rows": (10000, 100, 200000),
    "bulk_access_alert_per_hour": (60, 10, 5000),
    "bulk_access_block_per_hour": (300, 20, 20000),
}
BOOLEANS = {
    "mask_contact_details": True,       # mobile 98765XXXXX, email atr***@example.com in staff screens
    "reveal_requires_reauth": True,     # password / code again before a full number or address is shown
    "watermark_enabled": True,          # user, date-time and session on sensitive screens and exported PDFs
    "doctors_see_own_patients_only": True,  # doctors and professionals: only patients they have appointments with
    "lock_when_hidden": False,          # lock as soon as the tab is hidden (shared reception computers)
}
PRINT_POLICIES = ("allow", "warn", "block")
DEFAULTS: dict[str, Any] = {
    **{k: v[0] for k, v in LIMITS.items()},
    **BOOLEANS,
    "print_policy": "warn",
    "lock_after_minutes_by_role": {"receptionist": 10},
}


def validate_privacy_values(values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    for key, (_, lo, hi) in LIMITS.items():
        if key in out:
            v = out[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ValidationFailed(f"{key.replace('_', ' ').capitalize()} must be from {lo:g} to {hi:g}.", code="invalid_privacy_setting")
            out[key] = float(v) if key == "watermark_opacity" else int(v)
    for key in BOOLEANS:
        if key in out and not isinstance(out[key], bool):
            raise ValidationFailed(f"{key} must be true or false.", code="invalid_privacy_setting")
    if "print_policy" in out and out["print_policy"] not in PRINT_POLICIES:
        raise ValidationFailed("Printing must be allow, warn or block.", code="invalid_privacy_setting")
    if "lock_after_minutes_by_role" in out:
        by_role = out["lock_after_minutes_by_role"]
        if not isinstance(by_role, dict) or any(r not in ROLE_CODES for r in by_role) or any(
                isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= 240 for m in by_role.values()):
            raise ValidationFailed("Screen lock per role: minutes from 1 to 240 for known roles.", code="invalid_privacy_setting")
    if out.get("bulk_access_block_per_hour", 10**9) < out.get("bulk_access_alert_per_hour", 0):
        raise ValidationFailed("The blocking limit must be at least the alert limit.", code="invalid_privacy_setting")
    return out


def policy(db: Session, org: Organization | None) -> dict[str, Any]:
    if org is None:
        return dict(DEFAULTS)
    cache = db.info.setdefault("privacy_policy", {})
    if org.id not in cache:
        from app.services.organization_service import OrganizationService

        stored = OrganizationService(db).get_settings(org, "privacy")["privacy"]
        cache[org.id] = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    return cache[org.id]


def lock_minutes(pol: dict[str, Any], role_code: str | None) -> int:
    return int((pol.get("lock_after_minutes_by_role") or {}).get(role_code or "", pol["lock_after_minutes"]))


# ------------------------------------------------------------------------------------------------------------ masking
def mask_mobile(value: str | None) -> str | None:
    """+919876543210 -> +9198765XXXXX (country code, first 5 digits of the number, the rest hidden)."""
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) < 6:
        return "X" * len(digits)
    national = digits[-10:] if len(digits) > 10 else digits
    country = digits[: len(digits) - len(national)]
    shown = national[:5]
    return f"{'+' + country if value.startswith('+') and country else country}{shown}{'X' * (len(national) - len(shown))}"


def mask_email(value: str | None) -> str | None:
    """atreya.patel@example.com -> atr***@example.com"""
    if not value or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    keep = local[:3] if len(local) > 3 else local[:1]
    return f"{keep}***@{domain}"


def masking_on(db: Session) -> bool:
    """Set per request by the tenant dependency: True for staff (not customers, not API keys) when the clinic masks."""
    return bool(db.info.get("mask_contacts"))


def view_mobile(db: Session, value: str | None) -> str | None:
    return mask_mobile(value) if masking_on(db) else value


def view_email(db: Session, value: str | None) -> str | None:
    return mask_email(value) if masking_on(db) else value


def is_masked_echo(new: str | None, current: str | None) -> bool:
    """A form that loaded a masked value and sent it back unchanged must not overwrite the real number or address."""
    return bool(new and current and new in {mask_mobile(current), mask_email(current)} and new != current)


# ------------------------------------------------------------------------------------------------- re-authentication
def require_recent_auth(db: Session, request, org: Organization | None, *, action: str) -> None:
    """Sensitive actions need the password / code again if the last one was longer ago than the clinic allows.
    A fresh sign-in counts. API keys (integrations set up by an administrator) are not asked."""
    from app.models import UserSession

    if getattr(request.state, "api_key", None) is not None:
        return
    sid = getattr(request.state, "session_public_id", None)
    session = db.scalar(select(UserSession).where(UserSession.public_id == sid)) if sid else None
    window = timedelta(minutes=policy(db, org)["reauth_window_minutes"])
    if session is None or session.reauthenticated_at is None or utcnow() - session.reauthenticated_at > window:
        security_event("reauth_required")
        raise PermissionDenied("Please confirm it is you before you continue.", code="reauth_required",
                               data={"action": action, "window_minutes": int(window.total_seconds() // 60)})


# -------------------------------------------------------------------------------------------------- bulk detection
VIEW_ACTIONS = ("customer.viewed", "customer.notes_viewed", "customer.documents_viewed", "customer.contact_revealed",
                "customer.document_downloaded")


def check_bulk_access(db: Session, org: Organization, actor_id: int | None, entity_id: str) -> None:
    """Called before a patient record is opened. Many different patients in an hour from one person is unusual:
    first an alert (audit + security metric), then a block until the hour has passed."""
    if actor_id is None:
        return
    pol = policy(db, org)
    since = utcnow() - timedelta(hours=1)
    distinct = db.scalar(select(func.count(func.distinct(AuditLog.entity_id))).where(
        AuditLog.organization_id == org.id, AuditLog.actor_user_id == actor_id, AuditLog.action.in_(VIEW_ACTIONS),
        AuditLog.created_at >= since)) or 0
    seen = db.scalar(select(AuditLog.id).where(AuditLog.organization_id == org.id, AuditLog.actor_user_id == actor_id,
                                                AuditLog.action.in_(VIEW_ACTIONS), AuditLog.entity_id == entity_id,
                                                AuditLog.created_at >= since).limit(1)) is not None
    if seen:
        return  # opening the same patient again is normal
    if distinct >= pol["bulk_access_block_per_hour"]:
        security_event("bulk_access_blocked")
        raise RateLimited("You have opened an unusually large number of patient records in the last hour. "
                          "Please wait, or ask an administrator.", code="bulk_access_blocked")
    if distinct + 1 == pol["bulk_access_alert_per_hour"]:
        from app.services.audit_service import record_audit

        security_event("bulk_access_alert")
        record_audit(db, action="security.bulk_access_detected", actor=None, organization_id=org.id, entity_type="user",
                     entity_id=str(actor_id), after={"distinct_patients_last_hour": distinct + 1})


# -------------------------------------------------------------------------------------------------------- exports
EXPORT_ACTIONS = ("customer.exported", "report.exported", "customer.summary_exported", "reconciliation.exported",
                  "platform.organizations_exported", "customer.document_link_created")


def check_export_allowed(db: Session, org: Organization | None, actor_id: int | None, rows: int | None = None) -> None:
    pol = policy(db, org)
    if rows is not None and rows > pol["max_export_rows"]:
        security_event("export_refused")
        raise ValidationFailed(f"This export would have {rows:,} rows; the limit is {pol['max_export_rows']:,}. "
                               "Narrow the date range or filters.", code="export_too_large")
    if actor_id is None:
        return
    since = utcnow() - timedelta(days=1)
    q = select(func.count()).select_from(AuditLog).where(AuditLog.actor_user_id == actor_id, AuditLog.action.in_(EXPORT_ACTIONS),
                                                         AuditLog.created_at >= since)
    if org is not None:
        q = q.where(AuditLog.organization_id == org.id)
    if (db.scalar(q) or 0) >= pol["max_exports_per_day"]:
        security_event("export_refused")
        raise RateLimited(f"You have reached today's limit of {pol['max_exports_per_day']} exports.", code="export_limit")
    security_event("export")
