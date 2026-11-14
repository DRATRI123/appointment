from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, Meta, TenantContext, require_permission
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.models import AuditLog
from app.schemas.audit import AuditLogRead
from app.schemas.common import Message
from app.schemas.membership import MemberInvite, MemberRead, MemberUpdate
from app.schemas.organization import (
    DomainCreate,
    DomainRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationSettingsRead,
    OrganizationSettingsUpdate,
    OrganizationUpdate,
)
from app.schemas.role import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from app.schemas.user import UserRead
from app.services.membership_service import MembershipService
from app.services.organization_service import OrganizationService
from app.services.role_service import RoleService, role_to_read

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _member_read(m) -> MemberRead:
    return MemberRead(
        id=m.public_id, user=UserRead.model_validate(m.user), role_code=m.role.code, role_name=m.role.name,
        branch_id=m.branch.public_id if m.branch else None, status=m.status, invited_at=m.invited_at,
        accepted_at=m.accepted_at, created_at=m.created_at,
    )


# ----------------------------------------------------------------- own orgs
@router.get("", response_model=list[OrganizationRead], summary="Organizations the current user belongs to")
def list_my_organizations(db: DB, user: CurrentUser) -> list[OrganizationRead]:
    return [OrganizationRead.model_validate(o) for o in OrganizationService(db).list_for_user(user)]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED, summary="Create an organization (you become its owner)")
def create_organization(payload: OrganizationCreate, db: DB, user: CurrentUser, meta: Meta) -> OrganizationRead:
    return OrganizationRead.model_validate(OrganizationService(db, meta).create(payload, user))


@router.get("/by-slug/{slug}", response_model=OrganizationRead, summary="Public organization profile by slug")
def get_by_slug(slug: str, db: DB) -> OrganizationRead:
    return OrganizationRead.model_validate(OrganizationService(db).get_by_slug_public(slug))


# ------------------------------------------------------------ organization
@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(ctx: Annotated[TenantContext, Depends(require_permission("organization:read"))]) -> OrganizationRead:
    return OrganizationRead.model_validate(ctx.organization)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    payload: OrganizationUpdate, db: DB, meta: Meta,
    ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))],
) -> OrganizationRead:
    return OrganizationRead.model_validate(OrganizationService(db, meta).update(ctx.organization, payload, ctx.user))


# ----------------------------------------------------------------- settings
@router.get("/{organization_id}/settings", response_model=dict[str, dict])
def get_settings(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("organization:read"))]) -> dict:
    return OrganizationService(db).get_settings(ctx.organization)


@router.get("/{organization_id}/settings/{namespace}", response_model=OrganizationSettingsRead)
def get_settings_namespace(
    namespace: str, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("organization:read"))]
) -> OrganizationSettingsRead:
    values = OrganizationService(db).get_settings(ctx.organization, namespace)[namespace]
    return OrganizationSettingsRead(namespace=namespace, values=values)


@router.put("/{organization_id}/settings/{namespace}", response_model=OrganizationSettingsRead)
def put_settings_namespace(
    namespace: str, payload: OrganizationSettingsUpdate, db: DB, meta: Meta,
    ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))],
) -> OrganizationSettingsRead:
    values = OrganizationService(db, meta).update_settings(ctx.organization, namespace, payload.values, ctx.user)
    return OrganizationSettingsRead(namespace=namespace, values=values)


# ------------------------------------------------------------------ domains
@router.get("/{organization_id}/domains", response_model=list[DomainRead])
def list_domains(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("organization:read"))]) -> list[DomainRead]:
    return [DomainRead.model_validate(d) for d in OrganizationService(db).list_domains(ctx.organization)]


@router.post("/{organization_id}/domains", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
def add_domain(
    payload: DomainCreate, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))]
) -> DomainRead:
    return DomainRead.model_validate(OrganizationService(db, meta).add_domain(ctx.organization, payload, ctx.user))


@router.delete("/{organization_id}/domains/{domain_id}", response_model=Message)
def remove_domain(
    domain_id: int, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("organization:write"))]
) -> Message:
    OrganizationService(db, meta).remove_domain(ctx.organization, domain_id, ctx.user)
    return Message(detail="Domain removed.")


# ------------------------------------------------------------------ members
@router.get("/{organization_id}/members", response_model=list[MemberRead])
def list_members(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("staff:read"))]) -> list[MemberRead]:
    return [_member_read(m) for m in MembershipService(db).list_members(ctx.organization)]


@router.post("/{organization_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def invite_member(
    payload: MemberInvite, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("staff:write"))]
) -> MemberRead:
    m = MembershipService(db, meta).invite(ctx.organization, payload, ctx.user, ctx.role_code)
    db.refresh(m)
    return _member_read(m)


@router.patch("/{organization_id}/members/{membership_id}", response_model=MemberRead)
def update_member(
    membership_id: str, payload: MemberUpdate, db: DB, meta: Meta,
    ctx: Annotated[TenantContext, Depends(require_permission("staff:write"))],
) -> MemberRead:
    return _member_read(MembershipService(db, meta).update(ctx.organization, membership_id, payload, ctx.user, ctx.role_code))


@router.delete("/{organization_id}/members/{membership_id}", response_model=Message)
def remove_member(
    membership_id: str, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("staff:write"))]
) -> Message:
    MembershipService(db, meta).remove(ctx.organization, membership_id, ctx.user)
    return Message(detail="Member removed.")


# -------------------------------------------------------------------- roles
@router.get("/{organization_id}/roles", response_model=list[RoleRead])
def list_roles(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("staff:read"))]) -> list[RoleRead]:
    return [role_to_read(r) for r in RoleService(db).list_roles(ctx.organization)]


@router.get("/{organization_id}/permissions", response_model=list[PermissionRead])
def list_permissions(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("staff:read"))]) -> list[PermissionRead]:
    return [PermissionRead.model_validate(p) for p in RoleService(db).list_permissions() if not p.code.startswith("platform:")]


@router.post("/{organization_id}/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("roles:write"))]
) -> RoleRead:
    return role_to_read(RoleService(db, meta).create(ctx.organization, payload, ctx.user, ctx.permissions))


@router.patch("/{organization_id}/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: int, payload: RoleUpdate, db: DB, meta: Meta,
    ctx: Annotated[TenantContext, Depends(require_permission("roles:write"))],
) -> RoleRead:
    return role_to_read(RoleService(db, meta).update(ctx.organization, role_id, payload, ctx.user, ctx.permissions))


@router.delete("/{organization_id}/roles/{role_id}", response_model=Message)
def delete_role(role_id: int, db: DB, meta: Meta, ctx: Annotated[TenantContext, Depends(require_permission("roles:write"))]) -> Message:
    RoleService(db, meta).delete(ctx.organization, role_id, ctx.user)
    return Message(detail="Role deleted.")


# --------------------------------------------------------------- audit logs
@router.get("/{organization_id}/audit-logs", response_model=Page[AuditLogRead])
def list_audit_logs(
    db: DB,
    ctx: Annotated[TenantContext, Depends(require_permission("audit_logs:read"))],
    params: Annotated[PageParams, Depends(page_params)],
    action: Annotated[str | None, Query(max_length=64)] = None,
    entity_type: Annotated[str | None, Query(max_length=48)] = None,
) -> Page[AuditLogRead]:
    stmt = select(AuditLog).where(AuditLog.organization_id == ctx.organization.id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset(params.offset).limit(params.page_size)).all()
    return Page(data=[AuditLogRead.model_validate(r) for r in rows], meta=PageMeta(page=params.page, page_size=params.page_size, total=int(total)))
