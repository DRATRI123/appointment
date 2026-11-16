"""Platform super-admin endpoints."""
from __future__ import annotations

from datetime import date as _date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import DB, Meta, PlatformAdmin, recent_auth
from app.core.database import writes_on_read
from app.core.enums import UserStatus
from app.core.exceptions import NotFoundError, PermissionDenied
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.models import AuditLog, User
from app.schemas.audit import AuditLogRead
from app.schemas.common import APIModel
from app.schemas.organization import OrganizationRead, OrganizationStatusUpdate
from app.schemas.platform import OrgOverview, OrgSummary, Plan, PlatformDashboard, PlatformSettings, SubscriptionRead, SubscriptionUpdate
from app.schemas.user import UserRead
from app.services.audit_service import record_audit
from app.services.organization_service import OrganizationService
from app.services.platform_service import PlatformService, plans, platform_settings

router = APIRouter(prefix="/platform", tags=["platform"])


class UserStatusUpdate(APIModel):
    status: str
    reason: str | None = None


class PlatformStats(APIModel):
    organizations_total: int
    organizations_active: int
    users_total: int
    audit_events_24h: int


@router.get("/stats", response_model=PlatformStats)
def stats(db: DB, _: PlatformAdmin) -> PlatformStats:
    from datetime import timedelta

    from app.core.time import utcnow
    from app.models import Organization

    orgs_total = db.scalar(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))) or 0
    orgs_active = db.scalar(
        select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None), Organization.status == "active")
    ) or 0
    users_total = db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0
    since = utcnow() - timedelta(hours=24)
    events = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= since)) or 0
    return PlatformStats(organizations_total=orgs_total, organizations_active=orgs_active, users_total=users_total, audit_events_24h=events)


@router.get("/organizations", response_model=Page[OrganizationRead])
def list_organizations(
    db: DB, _: PlatformAdmin, params: Annotated[PageParams, Depends(page_params)],
    status: Annotated[str | None, Query()] = None, search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[OrganizationRead]:
    rows, total = OrganizationService(db).list_all(status=status, search=search, page=params.page, page_size=params.page_size)
    return Page(data=[OrganizationRead.model_validate(o) for o in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/organizations/{organization_id}", response_model=OrganizationRead)
def get_organization(organization_id: str, db: DB, _: PlatformAdmin) -> OrganizationRead:
    return OrganizationRead.model_validate(OrganizationService(db).get_or_404(organization_id))


@router.post("/organizations/{organization_id}/status", response_model=OrganizationRead, dependencies=[recent_auth("platform")])
def set_organization_status(organization_id: str, payload: OrganizationStatusUpdate, db: DB, admin: PlatformAdmin, meta: Meta) -> OrganizationRead:
    service = OrganizationService(db, meta)
    org = service.get_or_404(organization_id)
    return OrganizationRead.model_validate(service.set_status(org, payload.status, admin, payload.reason))


@router.get("/users", response_model=Page[UserRead])
def list_users(
    db: DB, _: PlatformAdmin, params: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(max_length=100)] = None, status: Annotated[str | None, Query()] = None,
) -> Page[UserRead]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(User.full_name).like(like) | func.lower(User.email).like(like) | User.mobile.like(like))
    if status:
        stmt = stmt.where(User.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset(params.offset).limit(params.page_size)).all()
    return Page(data=[UserRead.model_validate(u) for u in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=int(total)))


@router.post("/users/{user_id}/sessions/revoke", response_model=dict, dependencies=[recent_auth("platform")],
             summary="Sign an account out on every device now")
def revoke_user_sessions(user_id: str, db: DB, admin: PlatformAdmin, meta: Meta) -> dict:
    from app.services.auth_service import AuthService

    user = db.scalar(select(User).where(User.public_id == user_id))
    if user is None:
        raise NotFoundError("User not found.")
    count = AuthService(db, meta).revoke_all_sessions(user, reason="revoked_by_platform")
    record_audit(db, action="platform.sessions_revoked", actor=admin, entity_type="user", entity_id=user.public_id, after={"sessions": count}, meta=meta)
    return {"detail": f"Signed out of {count} device(s).", "sessions": count}


@router.post("/users/{user_id}/status", response_model=UserRead, dependencies=[recent_auth("platform")])
def set_user_status(user_id: str, payload: UserStatusUpdate, db: DB, admin: PlatformAdmin, meta: Meta) -> UserRead:
    if payload.status not in {s.value for s in UserStatus}:
        raise NotFoundError("Unknown status.")
    user = db.scalar(select(User).where(User.public_id == user_id))
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == admin.id and payload.status != UserStatus.ACTIVE:
        raise PermissionDenied("You cannot suspend yourself.", code="self_change")
    before = user.status
    user.status = payload.status
    if payload.status == UserStatus.SUSPENDED:
        from app.services.auth_service import AuthService

        AuthService(db, meta).revoke_all_sessions(user, reason="suspended")
    db.flush()
    record_audit(db, action=f"platform.user_{payload.status}", actor=admin, entity_type="user", entity_id=user.public_id,
                 before={"status": before}, after={"status": payload.status}, purpose=payload.reason, meta=meta)
    return UserRead.model_validate(user)


@router.get("/audit-logs", response_model=Page[AuditLogRead])
def platform_audit_logs(db: DB, _: PlatformAdmin, params: Annotated[PageParams, Depends(page_params)]) -> Page[AuditLogRead]:
    stmt = select(AuditLog)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset(params.offset).limit(params.page_size)).all()
    return Page(data=[AuditLogRead.model_validate(r) for r in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=int(total)))


# ---------------------------------------------------------------- dashboard, plans, subscriptions


@router.get("/dashboard", response_model=PlatformDashboard, summary="Platform KPIs and trends")
def platform_dashboard(db: DB, admin: PlatformAdmin, days: Annotated[int, Query(ge=7, le=365)] = 30):
    return PlatformService(db, admin).dashboard(days)


@router.get("/settings", response_model=PlatformSettings)
def get_platform_settings(db: DB, _: PlatformAdmin):
    return platform_settings(db)


@router.put("/settings", response_model=PlatformSettings, dependencies=[recent_auth("platform")])
def put_platform_settings(payload: PlatformSettings, db: DB, admin: PlatformAdmin, meta: Meta):
    return PlatformService(db, admin, meta).save_settings(payload)


@router.get("/plans", response_model=list[Plan])
def get_plans(db: DB, _: PlatformAdmin):
    return plans(db)


@router.put("/plans", response_model=list[Plan], dependencies=[recent_auth("platform")], summary="Replace the plan catalogue")
def put_plans(payload: list[Plan], db: DB, admin: PlatformAdmin, meta: Meta):
    return PlatformService(db, admin, meta).save_plans(payload)


@router.get("/subscriptions", response_model=list[OrgSummary], summary="Organizations with their current plan, usage and limit breaches")
def subscriptions(db: DB, admin: PlatformAdmin, search: Annotated[str | None, Query(max_length=100)] = None, plan: str | None = None,
                  status: str | None = None, over_limit: bool = False):
    return PlatformService(db, admin).summaries(search=search, plan=plan, status=status, over_limit=over_limit)


@router.get("/organizations/{organization_id}/overview", response_model=OrgOverview)
def organization_overview(organization_id: str, db: DB, admin: PlatformAdmin):
    svc = PlatformService(db, admin)
    return svc.overview(svc.org(organization_id))


@router.get("/organizations/{organization_id}/subscriptions", response_model=list[SubscriptionRead])
def subscription_history(organization_id: str, db: DB, admin: PlatformAdmin):
    svc = PlatformService(db, admin)
    return svc.history(svc.org(organization_id))


@router.put("/organizations/{organization_id}/subscription", response_model=OrgSummary, summary="Record a plan change (no payment is taken)")
def set_subscription(organization_id: str, payload: SubscriptionUpdate, db: DB, admin: PlatformAdmin, meta: Meta):
    svc = PlatformService(db, admin, meta)
    org = svc.org(organization_id)
    svc.set_subscription(org, payload)
    return svc.summary(org)


@router.get("/exports/organizations", summary="Organizations with plan and usage as CSV or Excel")
@writes_on_read  # access is audit-logged
def export_organizations(request: Request, db: DB, admin: PlatformAdmin, meta: Meta, format: Annotated[str, Query(pattern=r"^(csv|xlsx)$")] = "csv"):  # noqa: A002
    from app.services.privacy_service import check_export_allowed, require_recent_auth
    from app.services.report_service import Column, ReportDef, to_csv, to_xlsx

    require_recent_auth(db, request, None, action="export")
    check_export_allowed(db, None, admin.id)

    rows = []
    for s in PlatformService(db, admin).summaries(search=None, plan=None, status=None, over_limit=False):
        sub = s.subscription
        rows.append({"name": s.name, "slug": s.slug, "status": s.status, "created": s.created_at.date(), "plan": sub.plan_name if sub else "", "plan_status": sub.status if sub else "",
                     "branches": s.usage.branches, "professionals": s.usage.professionals, "staff": s.usage.staff, "customers": s.usage.customers,
                     "appointments_30d": s.usage.appointments_30d, "receipts_30d": s.usage.verified_receipts_30d_paise, "over_limit": ", ".join(s.over_limit)})
    report = ReportDef("organizations", "Organizations", "All organizations with plan and 30-day usage.", [
        Column("name", "Organization"), Column("slug", "Slug"), Column("status", "Status"), Column("created", "Created", "date"), Column("plan", "Plan"),
        Column("plan_status", "Plan status"), Column("branches", "Branches", "int"), Column("professionals", "Professionals", "int"), Column("staff", "Staff", "int"),
        Column("customers", "Customers", "int"), Column("appointments_30d", "Appointments (30 days)", "int"), Column("receipts_30d", "Verified receipts (30 days)", "money"),
        Column("over_limit", "Over limit")], lambda ctx: iter(()), totals=("appointments_30d", "receipts_30d"))
    record_audit(db, action="platform.organizations_exported", actor=admin, entity_type="report", entity_id="organizations", after={"format": format, "rows": len(rows)}, meta=meta)
    stamp = _date.today().isoformat()
    headers = {"Content-Disposition": f'attachment; filename="organizations_{stamp}.{format}"', "Cache-Control": "no-store"}
    if format == "csv":
        return Response(to_csv(report, rows), media_type="text/csv; charset=utf-8", headers=headers)
    return Response(to_xlsx(report, rows, owner="Platform", period=f"as of {stamp}", filters_label="", truncated=False),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@router.get("/api-usage", summary="API requests, keys and webhook delivery health per organization")
def api_usage(db: DB, _: PlatformAdmin, days: Annotated[int, Query(ge=1, le=90)] = 30):
    from app.services.developer_service import platform_usage

    return [u.model_dump() for u in platform_usage(db, days)]


@router.get("/system-status", summary="Worker, background jobs, backlog, backups and readiness checks")
def system_status_view(db: DB, _: PlatformAdmin):
    from sqlalchemy import text as _text

    from app.core.config import get_settings
    from app.core.observability import migration_head, storage_writable
    from app.services.ops_service import system_status

    settings = get_settings()
    status = system_status(db)
    current = db.execute(_text("SELECT version_num FROM alembic_version")).scalar()
    head = migration_head()
    status["checks"] = {
        "database": {"ok": True, "detail": "sqlite" if settings.is_sqlite else "postgresql"},
        "migrations": {"ok": current == head, "detail": f"at {current}" + ("" if current == head else f", release needs {head}")},
        "storage": {"ok": storage_writable(settings), "detail": settings.storage_backend},
        "error_tracking": {"ok": True, "detail": "Sentry on" if settings.sentry_dsn else "off (set SENTRY_DSN to enable)"},
        "metrics": {"ok": True, "detail": "on" if settings.metrics_token else "off (set METRICS_TOKEN to enable /metrics)"},
    }
    if not status["checks"]["migrations"]["ok"]:
        status["status"] = "attention"
        status["attention"].append("Database migrations are pending: run `alembic upgrade head`.")
    return status
