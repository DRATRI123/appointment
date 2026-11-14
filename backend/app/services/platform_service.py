"""Platform administration: settings, subscription plans and limits, tenant usage and the platform dashboard.

The platform never collects money from clinics through a gateway; subscriptions are recorded by platform staff.
Plan limits are enforced when a clinic adds branches, professionals or staff. An organization without a
subscription is unlimited (self-hosted single-clinic installs).
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import PaymentStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import (
    Appointment,
    AuditLog,
    Branch,
    Customer,
    Integration,
    Notification,
    Organization,
    OrganizationMembership,
    OrganizationSubscription,
    Payment,
    Professional,
    SystemSetting,
    User,
)
from app.schemas.platform import (
    LIMIT_KEYS,
    OrgOverview,
    OrgSummary,
    Plan,
    PlatformDashboard,
    PlatformDayPoint,
    PlatformSettings,
    PublicPlatform,
    SubscriptionRead,
    SubscriptionUpdate,
    Usage,
)
from app.services.audit_service import RequestMeta, record_audit

SETTINGS_KEY = "platform.settings"
PLANS_KEY = "platform.plans"
LIMITED_STATUSES = ("trial", "active", "past_due")
LIMIT_LABEL = {"branches": "branches", "professionals": "professionals", "staff": "staff members", "appointments_per_month": "appointments this month"}


def _get(db: Session, key: str) -> Any:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return (row.value or {}).get("v") if row else None


def _put(db: Session, key: str, value: Any, *, public: bool = False, description: str | None = None) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        row = SystemSetting(key=key, value={"v": value}, is_public=public, description=description)
        db.add(row)
    else:
        row.value = {"v": value}
    db.flush()


def platform_settings(db: Session) -> PlatformSettings:
    return PlatformSettings.model_validate(_get(db, SETTINGS_KEY) or {})


def public_platform(db: Session) -> PublicPlatform:
    s = platform_settings(db)
    return PublicPlatform(platform_name=s.platform_name, support_email=s.support_email, allow_organization_signup=s.allow_organization_signup,
                          announcement=s.announcement, announcement_level=s.announcement_level)


def plans(db: Session) -> list[Plan]:
    return [Plan.model_validate(p) for p in (_get(db, PLANS_KEY) or [])]


def current_subscription(db: Session, org_id: int) -> OrganizationSubscription | None:
    return db.scalar(select(OrganizationSubscription).where(OrganizationSubscription.organization_id == org_id)
                     .order_by(OrganizationSubscription.created_at.desc(), OrganizationSubscription.id.desc()))


def usage(db: Session, org_id: int, tz_name: str | None = None) -> Usage:
    from zoneinfo import ZoneInfo

    now = utcnow()
    local = now.astimezone(ZoneInfo(tz_name or "Asia/Kolkata"))
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    def count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    return Usage(
        branches=count(select(func.count()).select_from(Branch).where(Branch.organization_id == org_id, Branch.deleted_at.is_(None))),
        professionals=count(select(func.count()).select_from(Professional).where(Professional.organization_id == org_id, Professional.deleted_at.is_(None), Professional.is_active.is_(True))),
        staff=count(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == org_id, OrganizationMembership.status != "removed")),
        customers=count(select(func.count()).select_from(Customer).where(Customer.organization_id == org_id, Customer.deleted_at.is_(None))),
        appointments_this_month=count(select(func.count()).select_from(Appointment).where(Appointment.organization_id == org_id, Appointment.created_at >= month_start)),
        appointments_30d=count(select(func.count()).select_from(Appointment).where(Appointment.organization_id == org_id, Appointment.created_at >= now - timedelta(days=30))),
        verified_receipts_30d_paise=count(select(func.coalesce(func.sum(Payment.verified_amount_paise), 0)).where(
            Payment.organization_id == org_id, Payment.status.in_([PaymentStatus.VERIFIED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED]),
            Payment.verified_at >= now - timedelta(days=30))),
    )


def _over(sub: OrganizationSubscription | None, u: Usage) -> list[str]:
    if sub is None or sub.status not in LIMITED_STATUSES:
        return []
    limits = sub.limits or {}
    out = []
    for key in LIMIT_KEYS:
        limit = limits.get(key)
        current = u.appointments_this_month if key == "appointments_per_month" else getattr(u, key)
        if limit is not None and current > limit:
            out.append(key)
    return out


def check_limit(db: Session, org: Organization, resource: str, adding: int = 1) -> None:
    """Raise when adding ``resource`` would exceed the organization's plan."""
    sub = current_subscription(db, org.id)
    if sub is None or sub.status not in LIMITED_STATUSES:
        return
    limit = (sub.limits or {}).get(resource)
    if limit is None:
        return
    u = usage(db, org.id, org.timezone)
    current = u.appointments_this_month if resource == "appointments_per_month" else getattr(u, resource)
    if current + adding > limit:
        raise ConflictError(f"Your {sub.plan_name} plan allows {limit} {LIMIT_LABEL[resource]}. Contact the platform team to upgrade.", code="plan_limit")


def sub_read(s: OrganizationSubscription | None) -> SubscriptionRead | None:
    if s is None:
        return None
    return SubscriptionRead(id=s.public_id, plan_code=s.plan_code, plan_name=s.plan_name, status=s.status, price_paise=s.price_paise, billing_cycle=s.billing_cycle,
                            limits=s.limits or {}, starts_at=s.starts_at, ends_at=s.ends_at, trial_ends_at=s.trial_ends_at, cancelled_at=s.cancelled_at, notes=s.notes,
                            created_at=s.created_at)


def start_default_trial(db: Session, org: Organization) -> None:
    s = platform_settings(db)
    plan = next((p for p in plans(db) if p.code == s.default_plan_code and p.is_active), None)
    if plan is None:
        return
    now = utcnow()
    db.add(OrganizationSubscription(organization_id=org.id, plan_code=plan.code, plan_name=plan.name, status="trial", price_paise=plan.price_paise,
                                    billing_cycle=plan.billing_cycle, limits=plan.limits, starts_at=now,
                                    trial_ends_at=now + timedelta(days=s.default_trial_days) if s.default_trial_days else None, notes="Started automatically on sign-up"))
    db.flush()


class PlatformService:
    def __init__(self, db: Session, actor: User, meta: RequestMeta | None = None):
        self.db, self.actor, self.meta = db, actor, meta or RequestMeta()

    def _audit(self, action: str, entity_type: str, entity_id: str, *, before=None, after=None, organization_id: int | None = None) -> None:
        record_audit(self.db, action=action, actor=self.actor, organization_id=organization_id, entity_type=entity_type, entity_id=entity_id,
                     before=before, after=after, meta=self.meta)

    # ------------------------------------------------------------ settings & plans
    def save_settings(self, payload: PlatformSettings) -> PlatformSettings:
        if payload.default_plan_code and payload.default_plan_code not in {p.code for p in plans(self.db)}:
            raise ValidationFailed("The default plan does not exist.", code="unknown_plan")
        before = platform_settings(self.db).model_dump()
        _put(self.db, SETTINGS_KEY, payload.model_dump(), public=False, description="Platform settings")
        self._audit("platform.settings_updated", "system_setting", SETTINGS_KEY, before=before, after=payload.model_dump())
        return payload

    def save_plans(self, items: list[Plan]) -> list[Plan]:
        codes = [p.code for p in items]
        if len(codes) != len(set(codes)):
            raise ValidationFailed("Plan codes must be unique.", code="duplicate_plan")
        default = platform_settings(self.db).default_plan_code
        if default and default not in codes:
            raise ValidationFailed("The default plan cannot be removed. Choose another default first.", code="default_plan_in_use")
        before = [p.model_dump() for p in plans(self.db)]
        _put(self.db, PLANS_KEY, [p.model_dump() for p in items], description="Subscription plans")
        self._audit("platform.plans_updated", "system_setting", PLANS_KEY, before={"plans": before}, after={"plans": [p.model_dump() for p in items]})
        return items

    # ------------------------------------------------------------ organizations
    def org(self, public_id: str) -> Organization:
        org = self.db.scalar(select(Organization).where(Organization.public_id == public_id))
        if org is None:
            raise NotFoundError("Organization not found.")
        return org

    def summary(self, org: Organization) -> OrgSummary:
        sub = current_subscription(self.db, org.id)
        u = usage(self.db, org.id, org.timezone)
        return OrgSummary(id=org.public_id, name=org.name, slug=org.slug, status=org.status, created_at=org.created_at, subscription=sub_read(sub), usage=u, over_limit=_over(sub, u))

    def overview(self, org: Organization) -> OrgOverview:
        base = self.summary(org)
        owner = self.db.scalar(select(User).join(OrganizationMembership, OrganizationMembership.user_id == User.id).where(
            OrganizationMembership.organization_id == org.id).order_by(OrganizationMembership.id))
        events = self.db.scalars(select(AuditLog).where(AuditLog.organization_id == org.id).order_by(AuditLog.created_at.desc()).limit(15)).all()
        names = dict(self.db.execute(select(User.id, User.full_name).where(User.id.in_({e.actor_user_id for e in events if e.actor_user_id}))).all()) if events else {}
        return OrgOverview(**base.model_dump(), email=org.email, phone=org.phone, timezone=org.timezone, owner_name=owner.full_name if owner else None,
                           owner_contact=(owner.email or owner.mobile) if owner else None,
                           recent_activity=[{"action": e.action, "actor": names.get(e.actor_user_id), "at": e.created_at.isoformat()} for e in events])

    def summaries(self, *, search: str | None, plan: str | None, status: str | None, over_limit: bool) -> list[OrgSummary]:
        stmt = select(Organization).where(Organization.deleted_at.is_(None))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(Organization.name.ilike(like) | Organization.slug.ilike(like))
        out = []
        for org in self.db.scalars(stmt.order_by(Organization.created_at.desc()).limit(500)).all():
            s = self.summary(org)
            if plan and (s.subscription is None or s.subscription.plan_code != plan) and not (plan == "none" and s.subscription is None):
                continue
            if status and (s.subscription is None or s.subscription.status != status):
                continue
            if over_limit and not s.over_limit:
                continue
            out.append(s)
        return out

    def set_subscription(self, org: Organization, payload: SubscriptionUpdate) -> OrganizationSubscription:
        plan = next((p for p in plans(self.db) if p.code == payload.plan_code), None)
        if plan is None:
            raise ValidationFailed("Unknown plan.", code="unknown_plan")
        before = sub_read(current_subscription(self.db, org.id))
        now = utcnow()
        sub = OrganizationSubscription(
            organization_id=org.id, plan_code=plan.code, plan_name=plan.name, status=payload.status,
            price_paise=payload.price_paise if payload.price_paise is not None else plan.price_paise, billing_cycle=plan.billing_cycle, limits=plan.limits,
            starts_at=now, ends_at=payload.ends_at, trial_ends_at=payload.trial_ends_at, cancelled_at=now if payload.status == "cancelled" else None, notes=payload.notes,
        )
        self.db.add(sub)
        self.db.flush()
        self._audit("platform.subscription_changed", "organization", org.public_id, organization_id=org.id,
                    before=before.model_dump(mode="json") if before else None, after=sub_read(sub).model_dump(mode="json"))
        return sub

    def history(self, org: Organization) -> list[SubscriptionRead]:
        rows = self.db.scalars(select(OrganizationSubscription).where(OrganizationSubscription.organization_id == org.id)
                               .order_by(OrganizationSubscription.created_at.desc(), OrganizationSubscription.id.desc())).all()
        return [sub_read(r) for r in rows]

    # ------------------------------------------------------------ dashboard
    def dashboard(self, days: int) -> PlatformDashboard:
        now = utcnow()
        since = now - timedelta(days=days)

        def count(stmt) -> int:
            return int(self.db.scalar(stmt) or 0)

        appts = self.db.execute(select(Appointment.created_at, Appointment.organization_id).where(Appointment.created_at >= since)).all()
        signups = self.db.execute(select(Organization.created_at).where(Organization.created_at >= since, Organization.deleted_at.is_(None))).all()
        per_day_a, per_day_s = Counter(), Counter()
        for created, _ in appts:
            per_day_a[_day(created)] += 1
        for (created,) in signups:
            per_day_s[_day(created)] += 1
        start = _day(since)
        series = [PlatformDayPoint(date=start + timedelta(days=i), appointments=per_day_a[start + timedelta(days=i)], signups=per_day_s[start + timedelta(days=i)])
                  for i in range(days + 1)]
        top = Counter(org_id for _, org_id in appts).most_common(10)
        orgs = {o.id: o for o in self.db.scalars(select(Organization).where(Organization.id.in_([o for o, _ in top]))).all()} if top else {}
        sub_counts: Counter = Counter()
        for org in self.db.scalars(select(Organization).where(Organization.deleted_at.is_(None))).all():
            s = current_subscription(self.db, org.id)
            sub_counts[(s.plan_name, s.status) if s else ("No plan", "none")] += 1
        totals = {
            "organizations": count(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))),
            "organizations_active": count(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None), Organization.status == "active")),
            "organizations_new": len(signups),
            "users": count(select(func.count()).select_from(User).where(User.deleted_at.is_(None))),
            "users_new": count(select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.created_at >= since)),
            "appointments": len(appts),
            "verified_receipts_paise": count(select(func.coalesce(func.sum(Payment.verified_amount_paise), 0)).where(
                Payment.status.in_([PaymentStatus.VERIFIED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED]), Payment.verified_at >= since)),
            "notifications_sent": count(select(func.count()).select_from(Notification).where(Notification.status == "sent", Notification.sent_at >= since, Notification.channel != "in_app")),
            "notifications_failed": count(select(func.count()).select_from(Notification).where(Notification.status == "failed", Notification.updated_at >= since)),
            "integrations_in_error": count(select(func.count()).select_from(Integration).where(Integration.status == "error")),
        }
        return PlatformDashboard(days=days, totals=totals, series=series,
                                 top_organizations=[{"id": orgs[o].public_id, "name": orgs[o].name, "appointments": n} for o, n in top if o in orgs],
                                 plans=[{"plan": p, "status": st, "organizations": n} for (p, st), n in sub_counts.most_common()])


def _day(dt: datetime):
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC).date()
