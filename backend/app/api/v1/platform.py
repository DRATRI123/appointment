"""Platform super-admin endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DB, Meta, PlatformAdmin
from app.core.enums import UserStatus
from app.core.exceptions import NotFoundError, PermissionDenied
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.models import AuditLog, User
from app.schemas.audit import AuditLogRead
from app.schemas.common import APIModel
from app.schemas.organization import OrganizationRead, OrganizationStatusUpdate
from app.schemas.user import UserRead
from app.services.audit_service import record_audit
from app.services.organization_service import OrganizationService

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


@router.post("/organizations/{organization_id}/status", response_model=OrganizationRead)
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


@router.post("/users/{user_id}/status", response_model=UserRead)
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
