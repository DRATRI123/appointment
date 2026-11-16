"""Admin → Integrations hub, n8n incoming actions, Zoho OAuth callback, Tally export and follow-up tasks."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, Meta, TenantContext, get_tenant_context, recent_auth, require_permission
from app.core.database import writes_on_read
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models import Branch, Customer, FollowUpTask
from app.security.rate_limit import limiter
from app.services.connector_service import ConnectorService, zoho_connector_callback
from app.services.platform_config import runtime_settings

router = APIRouter(prefix="/integrations/hub", tags=["integration-hub"])
automation_router = APIRouter(prefix="/automation", tags=["integration-hub"])
storage_router = APIRouter(prefix="/integrations/hub", tags=["integration-hub"])  # registered before /{key}
ReadHub = Annotated[TenantContext, Depends(require_permission("integrations:read"))]
Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


class SaveBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict, description="Empty strings keep the stored secret")
    clear: list[str] = Field(default_factory=list)


class EnabledBody(BaseModel):
    enabled: bool


class TestBody(BaseModel):
    to: str | None = Field(default=None, max_length=254, description="Gmail: send a real test email to this address")


class ConnectBody(BaseModel):
    return_to: str = Field(default="/admin/integrations", max_length=300)


class RetryBody(BaseModel):
    item_id: int | None = None


def _svc(db, ctx: TenantContext, meta) -> ConnectorService:
    return ConnectorService(db, ctx.organization, ctx.user, meta, has=ctx.has)


@router.get("", summary="Every integration of this clinic with its real status, recent syncs and errors")
def overview(db: DB, ctx: ReadHub, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).overview()


@router.get("/tasks", summary="Follow-up tasks (created by staff or approved automations)")
def tasks(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("customers:read"))], status: str = Query(default="open")) -> list[dict[str, Any]]:
    rows = db.scalars(select(FollowUpTask).where(FollowUpTask.organization_id == ctx.organization.id, FollowUpTask.status == status)
                      .order_by(FollowUpTask.due_at.is_(None), FollowUpTask.due_at, FollowUpTask.id.desc()).limit(200)).all()
    out = []
    for t in rows:
        cust = db.get(Customer, t.customer_id) if t.customer_id else None
        out.append({"id": t.public_id, "title": t.title, "details": t.details, "due_at": t.due_at, "status": t.status, "source": t.source, "created_at": t.created_at,
                    "customer": {"id": cust.public_id, "name": cust.full_name} if cust and cust.deleted_at is None else None})
    return out


@router.post("/tasks/{task_id}/done", summary="Mark a follow-up task as done")
def task_done(task_id: str, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("customers:write"))]) -> dict[str, str]:
    t = db.scalar(select(FollowUpTask).where(FollowUpTask.public_id == task_id, FollowUpTask.organization_id == ctx.organization.id))
    if t is None:
        raise NotFoundError("Task not found.")
    t.status, t.completed_at, t.completed_by_user_id = "done", utcnow(), ctx.user.id
    return {"detail": "Done."}


@router.get("/zoho/callback", include_in_schema=False)
def zoho_callback(db: DB, state: str = "", code: str | None = None, error: str | None = None,
                  accounts_server: str | None = Query(default=None, alias="accounts-server")) -> RedirectResponse:
    return_to, outcome = zoho_connector_callback(db, code=code, state=state, error=error, accounts_server=accounts_server)
    sep = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{runtime_settings().frontend_url.rstrip('/')}{return_to}{sep}{urlencode({'connected': outcome})}", status_code=302)


@router.get("/tally/export", summary="Verified payments and refunds as a Tally import file (XML)")
@writes_on_read  # remembers what was exported; audit-logged
def tally_export(request: Request, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("payments:verify"))], meta: Meta,
                 from_date: date = Query(alias="from"), to_date: date = Query(alias="to"), branch_id: str | None = None,
                 include_exported: bool = False) -> Response:
    from app.connectors.accounting import tally_export as build
    from app.services.audit_service import record_audit
    from app.services.privacy_service import check_export_allowed, require_recent_auth

    if to_date < from_date or (to_date - from_date).days > 366:
        raise ValidationFailed("Choose a period of at most one year.", code="invalid_period")
    require_recent_auth(db, request, ctx.organization, action="export")
    svc = _svc(db, ctx, meta)
    integ = svc.row("tally")
    if integ is None or not integ.is_enabled:
        raise ValidationFailed("Set up Tally (ledger names) first.", code="integration_not_configured")
    branch = None
    if branch_id:
        branch = db.scalar(select(Branch).where(Branch.public_id == branch_id, Branch.organization_id == ctx.organization.id))
        if branch is None:
            raise NotFoundError("Branch not found.")
    if ctx.branch_id and (branch is None or branch.id != ctx.branch_id):
        raise PermissionDenied("You can export your own branch only.", code="branch_scope")
    check_export_allowed(db, ctx.organization, ctx.user.id)
    xml, count = build(db, ctx.organization, integ, start=from_date, end=to_date, branch_id=branch.id if branch else None, include_exported=include_exported)
    record_audit(db, action="integration.tally_exported", actor=ctx.user, organization_id=ctx.organization.id, entity_type="integration", entity_id=integ.public_id,
                 after={"from": str(from_date), "to": str(to_date), "branch": branch_id, "vouchers": count}, meta=meta)
    name = f"tally-{ctx.organization.slug}-{from_date}-{to_date}.xml"
    return Response(xml, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
                                                                "X-Voucher-Count": str(count)})


@router.get("/{key}", summary="One integration: settings (secrets hidden), status, logs, failed syncs, setup notes")
def detail(key: str, db: DB, ctx: ReadHub, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).detail(key)


@router.put("/{key}", summary="Save settings (secrets encrypted, shown once if generated)", dependencies=[recent_auth("integrations")])
def save(key: str, body: SaveBody, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).save(key, body.values, body.secrets, body.clear)


@router.post("/{key}/enabled", summary="Switch on or off without losing the settings")
def enabled(key: str, body: EnabledBody, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).set_enabled(key, body.enabled)


@router.post("/{key}/test", summary="Test the connection for real")
@limiter.limit("10/minute")
def test(request: Request, key: str, body: TestBody, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).test(key, body.to)


@router.post("/{key}/connect", summary="Start connecting the clinic's Google or Zoho account (returns the sign-in URL)")
def connect(key: str, body: ConnectBody, db: DB, ctx: Tenant, meta: Meta) -> dict[str, str]:
    return {"url": _svc(db, ctx, meta).oauth_start(key, body.return_to)}


@router.post("/{key}/disconnect", summary="Disconnect (tokens revoked where the provider allows it)", dependencies=[recent_auth("integrations")])
def disconnect(key: str, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).disconnect(key)


@router.post("/{key}/rotate", summary="Rotate generated secrets (n8n); the new ones are shown once", dependencies=[recent_auth("integrations")])
def rotate(key: str, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).rotate(key)


@router.post("/{key}/retry", summary="Retry failed syncs (one, or all)")
def retry(key: str, body: RetryBody, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).retry(key, body.item_id)


@router.post("/{key}/sync-all", summary="Send every existing record now (first connection)")
def sync_all(key: str, db: DB, ctx: Tenant, meta: Meta) -> dict[str, Any]:
    return _svc(db, ctx, meta).sync_all(key)


async def raw_body(request: Request) -> bytes:
    """The exact bytes that were signed (read before the handler runs in the thread pool)."""
    return await request.body()


@automation_router.post("/n8n/{integration_id}", summary="Signed incoming action from n8n (see docs/integrations/n8n-integration.md)")
@limiter.limit("60/minute")
def n8n_action(request: Request, integration_id: str, db: DB, body: Annotated[bytes, Depends(raw_body)]) -> JSONResponse:
    from app.services.automation_service import handle

    if len(body) > 64 * 1024:
        return JSONResponse({"code": "too_large", "detail": "Body larger than 64 KB."}, status_code=413)
    status, payload = handle(db, integration_id, request.headers, body)
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


class StorageSwitchBody(BaseModel):
    on: bool = Field(description="true: move this clinic's private files to its own bucket; false: move them back to the platform storage")


@storage_router.post("/own_storage/switch", summary="Move this clinic's private files to its own bucket (or back), checking every copy",
             dependencies=[recent_auth("integrations")])
def own_storage_switch(body: StorageSwitchBody, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))], meta: Meta) -> dict[str, Any]:
    from app.services.audit_service import record_audit
    from app.services.clinic_storage import request_switch

    st = request_switch(db, ctx.organization, on=body.on)
    record_audit(db, action="integration.storage_switch_requested", actor=ctx.user, organization_id=ctx.organization.id, entity_type="integration",
                 entity_id="own_storage", after={"direction": st["direction"]}, meta=meta)
    return _svc(db, ctx, meta).detail("own_storage")


@storage_router.get("/own_storage/usage", summary="Number and size of this clinic's private files where they are kept now")
def own_storage_usage(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))]) -> dict[str, Any]:
    from app.services.clinic_storage import usage

    return usage(db, ctx.organization)
