"""Dashboards (analytics) and exportable reports."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DB, Meta, TenantContext, get_tenant_context
from app.core.database import writes_on_read
from app.core.exceptions import NotFoundError, PermissionDenied
from app.core.time import utcnow
from app.models import Branch, Professional, Service
from app.schemas.analytics import Dashboard
from app.schemas.common import APIModel
from app.services.analytics_service import AnalyticsService, Filters
from app.services.audit_service import record_audit
from app.services.report_service import REPORTS, ReportContext, get_report, preview_value, run, to_csv, to_xlsx, totals

router = APIRouter(tags=["reports"])
Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


class FilterParams:
    def __init__(self, from_date: Annotated[date | None, Query(alias="from")] = None, to_date: Annotated[date | None, Query(alias="to")] = None,
                 branch_id: str | None = None, professional_id: str | None = None, service_id: str | None = None):
        self.from_date, self.to_date, self.branch_id, self.professional_id, self.service_id = from_date, to_date, branch_id, professional_id, service_id


def _resolve(db, ctx: TenantContext, p: FilterParams, *, own_professional: Professional | None = None) -> tuple[Filters, str]:
    org = ctx.organization
    today = utcnow().astimezone(ZoneInfo(org.timezone or "Asia/Kolkata")).date()
    to_date = p.to_date or today
    from_date = p.from_date or (to_date - timedelta(days=29))

    def lookup(model, public_id: str | None, what: str):
        if not public_id:
            return None
        row = db.scalar(select(model).where(model.public_id == public_id, model.organization_id == org.id))
        if row is None:
            raise NotFoundError(f"{what} not found.")
        return row

    branch = lookup(Branch, p.branch_id, "Branch")
    pro = own_professional or lookup(Professional, p.professional_id, "Professional")
    service = lookup(Service, p.service_id, "Service")
    label = ", ".join(x for x in [f"Branch: {branch.name}" if branch else "", f"Professional: {pro.display_name}" if pro else "", f"Service: {service.name}" if service else ""] if x)
    return Filters(org, from_date, to_date, branch_id=branch.id if branch else None, professional_id=pro.id if pro else None,
                   service_id=service.id if service else None), label


def _own_professional(db, ctx: TenantContext) -> Professional | None:
    return db.scalar(select(Professional).where(Professional.organization_id == ctx.organization.id, Professional.user_id == ctx.user.id, Professional.deleted_at.is_(None)))


@router.get("/analytics/dashboard", response_model=Dashboard, summary="KPIs, trends and breakdowns for a date range (clinic time zone)")
def dashboard(db: DB, ctx: Tenant, params: Annotated[FilterParams, Depends()], mine: Annotated[bool, Query(description="Only my own appointments (professionals)")] = False):
    if ctx.has("reports:read") and not mine:
        f, _ = _resolve(db, ctx, params)
        return AnalyticsService(db, ctx.organization).dashboard(f)
    own = _own_professional(db, ctx) if ctx.has("appointments:read_own") or ctx.has("appointments:read") else None
    if own is None:
        raise PermissionDenied("Missing permission: reports:read", code="permission_denied")
    f, _ = _resolve(db, ctx, params, own_professional=own)  # professionals only ever see their own numbers
    return AnalyticsService(db, ctx.organization).dashboard(f, scope="professional")


class ReportColumn(APIModel):
    key: str
    label: str
    type: str


class ReportInfo(APIModel):
    key: str
    title: str
    description: str
    columns: list[ReportColumn]
    contains_personal_data: bool
    can_export: bool


class ReportResult(APIModel):
    key: str
    title: str
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    totals: dict[str, Any]
    total_rows: int
    page: int
    page_size: int
    truncated: bool
    from_date: date
    to_date: date


def _info(r, ctx: TenantContext) -> ReportInfo:
    return ReportInfo(key=r.key, title=r.title, description=r.description, columns=[ReportColumn(key=c.key, label=c.label, type=c.type) for c in r.columns],
                      contains_personal_data=r.contains_personal_data, can_export=ctx.has("reports:export"))


@router.get("/reports", response_model=list[ReportInfo], summary="Reports available to the signed-in member")
def list_reports(ctx: Tenant):
    return [_info(r, ctx) for r in REPORTS.values() if all(ctx.has(p) for p in r.permissions)]


@router.get("/reports/{key}", response_model=ReportResult)
def report(key: str, db: DB, ctx: Tenant, params: Annotated[FilterParams, Depends()], page: Annotated[int, Query(ge=1)] = 1,
           page_size: Annotated[int, Query(ge=1, le=500)] = 100):
    r = get_report(key, ctx.has)
    f, _ = _resolve(db, ctx, params)
    rows, truncated = run(r, ReportContext(db, ctx.organization, f))
    chunk = rows[(page - 1) * page_size: page * page_size]
    return ReportResult(key=r.key, title=r.title, columns=_info(r, ctx).columns, rows=[{c.key: preview_value(row.get(c.key), c.type) for c in r.columns} for row in chunk],
                        totals=totals(r, rows), total_rows=len(rows), page=page, page_size=page_size, truncated=truncated, from_date=f.from_date, to_date=f.to_date)


@router.get("/reports/{key}/export", summary="Download a report as CSV or Excel (audit-logged)")
@writes_on_read  # access is audit-logged
def export(key: str, request: Request, db: DB, ctx: Tenant, meta: Meta, params: Annotated[FilterParams, Depends()],
           format: Annotated[str, Query(pattern=r"^(csv|xlsx)$")] = "csv"):  # noqa: A002 - query parameter name
    from app.services.privacy_service import check_export_allowed, require_recent_auth

    ctx.require("reports:export")
    r = get_report(key, ctx.has)
    if r.contains_personal_data:  # reports with patient names or numbers: confirm it is them first
        require_recent_auth(db, request, ctx.organization, action="export")
    f, label = _resolve(db, ctx, params)
    rows, truncated = run(r, ReportContext(db, ctx.organization, f))
    check_export_allowed(db, ctx.organization, ctx.user.id, rows=len(rows))
    record_audit(db, action="report.exported", actor=ctx.user, organization_id=ctx.organization.id, entity_type="report", entity_id=r.key,
                 after={"format": format, "from": f.from_date.isoformat(), "to": f.to_date.isoformat(), "filters": label, "rows": len(rows),
                        "personal_data": r.contains_personal_data}, meta=meta)
    name = f"{r.key}_{f.from_date.isoformat()}_{f.to_date.isoformat()}"
    headers = {"Content-Disposition": f'attachment; filename="{name}.{format}"', "Cache-Control": "no-store"}
    if format == "csv":
        return Response(to_csv(r, rows), media_type="text/csv; charset=utf-8", headers=headers)
    body = to_xlsx(r, rows, owner=ctx.organization.name, period=f"{f.from_date.isoformat()} to {f.to_date.isoformat()} ({f.tz})", filters_label=label,
                   truncated=truncated, tz=f.tz)
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

