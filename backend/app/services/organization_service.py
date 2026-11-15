from __future__ import annotations

import re
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import MembershipStatus, OrganizationStatus, SystemRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models import Organization, OrganizationDomain, OrganizationMembership, OrganizationSetting, User
from app.repositories.organizations import MembershipRepository, OrganizationRepository, RoleRepository
from app.schemas.organization import DomainCreate, OrganizationCreate, OrganizationUpdate
from app.services.audit_service import RequestMeta, record_audit

SETTING_NAMESPACES = {"branding", "booking", "cancellation", "payment", "notification", "legal", "general", "privacy", "embed", "otp", "security"}

# One-time-code policy for public bookings: (default, min, max) for numbers.
OTP_LIMITS = {
    "code_length": (6, 4, 6), "expiry_seconds": (300, 60, 900), "resend_cooldown_seconds": (60, 20, 600), "max_attempts": (5, 3, 10),
    "max_resends": (3, 1, 10), "limit_per_destination_hour": (5, 1, 10), "limit_per_ip_hour": (20, 5, 200), "limit_per_session_hour": (8, 2, 30),
}
OTP_CHANNELS = ("sms", "whatsapp", "email")


def validate_otp_values(values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    for key, (_, lo, hi) in OTP_LIMITS.items():
        if key in out:
            v = out[key]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise ValidationFailed(f"{key.replace('_', ' ').capitalize()} must be a whole number from {lo} to {hi}.", code="invalid_otp_setting")
    if "code_length" in out and out["code_length"] not in (4, 6):
        raise ValidationFailed("Codes can have 4 or 6 digits.", code="invalid_otp_setting")
    for key in ("enabled", "required_for_booking"):
        if key in out and not isinstance(out[key], bool):
            raise ValidationFailed(f"{key} must be true or false.", code="invalid_otp_setting")
    if "channels" in out:
        ch = out["channels"]
        if not isinstance(ch, list) or not ch or any(c not in OTP_CHANNELS for c in ch) or len(set(ch)) != len(ch):
            raise ValidationFailed("Choose at least one of SMS, WhatsApp and email.", code="invalid_otp_setting")
    if "default_channel" in out and out["default_channel"] not in OTP_CHANNELS:
        raise ValidationFailed("Choose SMS, WhatsApp or email as the default.", code="invalid_otp_setting")
    return out

# The public booking page lives at /<slug>, next to the app's own pages. These can never be a clinic's slug.
RESERVED_SLUGS = frozenset({
    "about", "admin", "api", "app", "auth", "book", "booking", "contact", "customer", "docs", "embed", "favicon-ico",
    "forgot-password", "health", "help", "login", "logout", "media", "metrics", "o", "onboarding", "pricing", "privacy",
    "professional", "redoc", "refund-policy", "register", "reset-password", "robots-txt", "settings", "signup", "sitemap-xml",
    "static", "super-admin", "support", "terms", "verify-email", "www",
})
EMBED_ORIGIN_RE = re.compile(r"^https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+(?::\d{1,5})?$")
DEV_EMBED_ORIGIN_RE = re.compile(r"^http://(?:localhost|127\.0\.0\.1|[a-z0-9-]+\.localhost|[a-z0-9.-]+\.test)(?::\d{1,5})?$")


def validate_embed_origins(value: Any) -> list[str]:
    """Exact origins (scheme://host[:port]) allowed to show the booking page in an iframe. HTTPS only, no wildcards;
    plain http is accepted only for local development hosts outside production."""
    from app.core.config import get_settings

    if not isinstance(value, list) or len(value) > 20:
        raise ValidationFailed("allowed_origins must be a list of at most 20 web addresses.", code="invalid_embed_origins")
    dev = get_settings().app_env in {"development", "test"}
    out: list[str] = []
    for raw in value:
        origin = str(raw).strip().lower().rstrip("/")
        if not (EMBED_ORIGIN_RE.fullmatch(origin) or (dev and DEV_EMBED_ORIGIN_RE.fullmatch(origin))):
            raise ValidationFailed(f"{raw!r} is not an allowed origin. Use the exact https:// address of your shop, e.g. "
                                   "https://www.yourclinic.com or https://your-store.myshopify.com (no paths, no wildcards).",
                                   code="invalid_embed_origin")
        if origin not in out:
            out.append(origin)
    return out

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "booking": {
        "allow_guest_booking": True,
        "min_notice_minutes": 60,
        "max_advance_days": 60,
        "hold_minutes": 10,
        "payment_window_minutes": 30,
        "allow_any_professional": True,
        "default_slot_minutes": 15,
        # Guests confirm their mobile number with a one-time code before an online booking is accepted.
        "require_mobile_verification": True,
    },
    # Websites (e.g. a Shopify store) allowed to show the booking page inside an iframe.
    "embed": {"allowed_origins": []},
    # Owners and administrators must use two-step sign-in (authenticator app) to manage the clinic.
    "security": {"require_admin_mfa": False},
    # One-time codes before an online booking is accepted (see app/services/otp).
    "otp": {"enabled": True, "required_for_booking": True, "channels": ["sms"], "default_channel": "sms", **{k: v[0] for k, v in OTP_LIMITS.items()}},
    "cancellation": {
        "customer_can_cancel": True,
        "cancel_before_hours": 4,
        "customer_can_reschedule": True,
        "reschedule_before_hours": 4,
        "max_reschedules": 2,
        "refund_policy": "manual_review",
        "auto_request_refund": True,  # open a refund *request* for eligible paid amounts when an appointment is cancelled
        "refund_requires_second_approver": False,  # maker-checker: the approver must differ from the requester
    },
    "payment": {
        "require_advance": True,
        "allow_pay_at_clinic": True,
        "allow_cash": True,
        "auto_expire_unpaid": True,
        "show_payment_instructions": True,
        "require_screenshot": False,
    },
    "notification": {
        "email_enabled": True,
        "sms_enabled": False,
        "whatsapp_enabled": False,
        "reminder_hours": [24, 2],
        "notify_staff_on_booking": True,
        "in_app_enabled": True,
        "reply_to_email": "",
        "events": {},  # {"appointment.reminder": {"enabled": true, "channels": ["email", "whatsapp"]}, ...}
    },
    "branding": {"primary_color": "#0f766e", "accent_color": "#14b8a6", "tagline": ""},
    "legal": {"privacy_policy": "", "terms": "", "refund_policy": ""},
    "general": {"business_hours": {}, "booking_page_enabled": True},
    "privacy": {
        "document_retention_days": 0,
        "consent_text": "I agree to the clinic storing my details to manage my appointments.",
        "require_consent_at_booking": False,
        "allow_customer_self_update": True,
    },
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "org"


class OrganizationService:
    def __init__(self, db: Session, meta: RequestMeta | None = None):
        self.db = db
        self.meta = meta or RequestMeta()
        self.orgs = OrganizationRepository(db)
        self.memberships = MembershipRepository(db)
        self.roles = RoleRepository(db)

    # ------------------------------------------------------------- create
    def create(self, payload: OrganizationCreate, owner: User) -> Organization:
        from app.services.platform_service import platform_settings

        if not owner.is_platform_admin and not platform_settings(self.db).allow_organization_signup:
            raise PermissionDenied("New organizations are not being accepted right now. Contact the platform team.", code="signup_closed")
        slug = payload.slug or slugify(payload.name)
        if slug in RESERVED_SLUGS:
            if payload.slug:
                raise ConflictError("This web address is reserved. Please choose another.", code="slug_reserved")
            slug = f"{slug}-{secrets.token_hex(2)}"
        if self.orgs.get_by_slug(slug):
            if payload.slug:
                raise ConflictError("This URL slug is already taken.", code="slug_taken")
            slug = f"{slug}-{secrets.token_hex(2)}"
        code = self._unique_code(payload.name)
        org = Organization(
            slug=slug,
            code=code,
            name=payload.name.strip(),
            legal_name=payload.legal_name,
            business_type=payload.business_type,
            email=payload.email,
            phone=payload.phone,
            website=payload.website,
            description=payload.description,
            address=payload.address,
            timezone=payload.timezone,
            currency=payload.currency.upper(),
            locale=payload.locale,
            status=OrganizationStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        self.orgs.add(org)
        owner_role = self.roles.get_system_role(SystemRole.ORG_OWNER)
        if owner_role is None:
            raise ValidationFailed("System roles are not seeded. Run scripts/seed.py.", code="roles_missing")
        self.memberships.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=owner.id,
                role_id=owner_role.id,
                status=MembershipStatus.ACTIVE,
                accepted_at=utcnow(),
            )
        )
        for namespace, values in DEFAULT_SETTINGS.items():
            for key, value in values.items():
                self.db.add(OrganizationSetting(organization_id=org.id, namespace=namespace, key=key, value={"v": value}))
        self.db.flush()
        record_audit(
            self.db, action="organization.created", actor=owner, organization_id=org.id,
            entity_type="organization", entity_id=org.public_id, after={"name": org.name, "slug": org.slug}, meta=self.meta,
        )
        from app.services.platform_service import start_default_trial

        start_default_trial(self.db, org)
        return org

    def _unique_code(self, name: str) -> str:
        base = re.sub(r"[^A-Z0-9]", "", name.upper())[:6] or "ORG"
        code = base
        attempt = 0
        while self.orgs.get_by_code(code):
            attempt += 1
            code = f"{base[:4]}{attempt:02d}"
        return code

    # --------------------------------------------------------------- read
    def get_or_404(self, public_id: str) -> Organization:
        org = self.orgs.get_by_public_id(public_id)
        if org is None or org.deleted_at is not None:
            raise NotFoundError("Organization not found.")
        return org

    def get_by_slug_public(self, slug: str) -> Organization:
        org = self.orgs.get_by_slug(slug)
        if org is None or org.deleted_at is not None or org.status != OrganizationStatus.ACTIVE:
            raise NotFoundError("Organization not found.")
        return org

    def list_for_user(self, user: User) -> list[Organization]:
        return [m.organization for m in self.memberships.list_for_user(user.id) if m.organization.deleted_at is None]

    def list_all(self, *, status: str | None, search: str | None, page: int, page_size: int) -> tuple[list[Organization], int]:
        stmt = select(Organization).where(Organization.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Organization.status == status)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Organization.name).like(like) | func.lower(Organization.slug).like(like))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(Organization.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    # ------------------------------------------------------------- update
    def update(self, org: Organization, payload: OrganizationUpdate, actor: User) -> Organization:
        data = payload.model_dump(exclude_unset=True)
        before = {k: getattr(org, k) for k in data}
        for key, value in data.items():
            setattr(org, key, value.upper() if key == "currency" and value else value)
        self.db.flush()
        record_audit(
            self.db, action="organization.updated", actor=actor, organization_id=org.id,
            entity_type="organization", entity_id=org.public_id, before=before, after=data, meta=self.meta,
        )
        return org

    def set_status(self, org: Organization, status: str, actor: User, reason: str | None) -> Organization:
        before = org.status
        org.status = status
        self.db.flush()
        record_audit(
            self.db, action=f"organization.{status}", actor=actor, organization_id=org.id,
            entity_type="organization", entity_id=org.public_id, before={"status": before}, after={"status": status},
            purpose=reason, meta=self.meta,
        )
        return org

    # ----------------------------------------------------------- settings
    def get_settings(self, org: Organization, namespace: str | None = None) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {ns: dict(vals) for ns, vals in DEFAULT_SETTINGS.items()}
        for row in self.orgs.list_settings(org.id, namespace):
            result.setdefault(row.namespace, {})[row.key] = (row.value or {}).get("v")
        if namespace:
            if namespace not in SETTING_NAMESPACES:
                raise NotFoundError("Unknown settings namespace.")
            return {namespace: result.get(namespace, {})}
        return result

    def update_settings(self, org: Organization, namespace: str, values: dict[str, Any], actor: User) -> dict[str, Any]:
        if namespace not in SETTING_NAMESPACES:
            raise NotFoundError("Unknown settings namespace.")
        before = self.get_settings(org, namespace)[namespace]
        if namespace == "embed" and "allowed_origins" in values:
            values = {**values, "allowed_origins": validate_embed_origins(values["allowed_origins"])}
        if namespace == "security":
            unknown = set(values) - {"require_admin_mfa"}
            if unknown or not isinstance(values.get("require_admin_mfa", False), bool):
                raise ValidationFailed("Only require_admin_mfa (true or false) can be set here.", code="invalid_setting")
            if values.get("require_admin_mfa") and actor.mfa_enabled_at is None:
                raise ValidationFailed("Turn on two-step sign-in for your own account first, so you are not locked out.", code="mfa_not_enabled")
        if namespace == "otp":
            values = validate_otp_values(values)
            merged = {**before, **values}
            if merged["default_channel"] not in merged["channels"]:
                raise ValidationFailed("The default method must be one of the enabled methods.", code="invalid_otp_setting")
        for key, value in values.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key):
                raise ValidationFailed(f"Invalid setting key: {key}", code="invalid_setting_key")
            row = self.orgs.get_setting(org.id, namespace, key)
            if row is None:
                self.db.add(OrganizationSetting(organization_id=org.id, namespace=namespace, key=key, value={"v": value}))
            else:
                row.value = {"v": value}
        self.db.flush()
        after = self.get_settings(org, namespace)[namespace]
        record_audit(
            self.db, action="organization.settings_updated", actor=actor, organization_id=org.id,
            entity_type="organization_settings", entity_id=namespace, before=before, after=after, meta=self.meta,
        )
        return after

    # ------------------------------------------------------------ domains
    def list_domains(self, org: Organization) -> list[OrganizationDomain]:
        return self.orgs.list_domains(org.id)

    def add_domain(self, org: Organization, payload: DomainCreate, actor: User) -> OrganizationDomain:
        domain = payload.domain.lower()
        if self.orgs.get_domain(domain):
            raise ConflictError("This domain is already registered.", code="domain_taken")
        if payload.is_primary:
            for d in self.orgs.list_domains(org.id):
                d.is_primary = False
        row = OrganizationDomain(
            organization_id=org.id,
            domain=domain,
            is_primary=payload.is_primary,
            verification_token=f"appt-verify-{secrets.token_hex(16)}",
        )
        self.db.add(row)
        self.db.flush()
        record_audit(self.db, action="organization.domain_added", actor=actor, organization_id=org.id,
                     entity_type="organization_domain", entity_id=domain, meta=self.meta)
        return row

    def remove_domain(self, org: Organization, domain_id: int, actor: User) -> None:
        row = self.db.get(OrganizationDomain, domain_id)
        if row is None or row.organization_id != org.id:
            raise NotFoundError("Domain not found.")
        self.db.delete(row)
        self.db.flush()
        record_audit(self.db, action="organization.domain_removed", actor=actor, organization_id=org.id,
                     entity_type="organization_domain", entity_id=row.domain, meta=self.meta)
