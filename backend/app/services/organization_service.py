from __future__ import annotations

import re
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import MembershipStatus, OrganizationStatus, SystemRole
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import Organization, OrganizationDomain, OrganizationMembership, OrganizationSetting, User
from app.repositories.organizations import MembershipRepository, OrganizationRepository, RoleRepository
from app.schemas.organization import DomainCreate, OrganizationCreate, OrganizationUpdate
from app.services.audit_service import RequestMeta, record_audit

SETTING_NAMESPACES = {"branding", "booking", "cancellation", "payment", "notification", "legal", "general", "privacy"}

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "booking": {
        "allow_guest_booking": True,
        "min_notice_minutes": 60,
        "max_advance_days": 60,
        "hold_minutes": 10,
        "payment_window_minutes": 30,
        "allow_any_professional": True,
        "default_slot_minutes": 15,
    },
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
        slug = payload.slug or slugify(payload.name)
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
