"""Shared FastAPI dependencies: database, current user, tenant context, permission guards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.enums import OrganizationStatus, UserStatus
from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models import Organization, OrganizationMembership, User
from app.repositories.organizations import MembershipRepository, OrganizationRepository
from app.repositories.users import SessionRepository, UserRepository
from app.security.permissions import PERMISSIONS
from app.security.tokens import decode_access_token
from app.services.audit_service import RequestMeta, record_audit

DB = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
ORG_HEADER = "X-Organization-Id"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_request_meta(request: Request) -> RequestMeta:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return RequestMeta(
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


Meta = Annotated[RequestMeta, Depends(get_request_meta)]


def _extract_token(request: Request) -> tuple[str | None, str]:
    """Return (token, source) where source is 'header' or 'cookie'."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip(), "header"
    cookie = request.cookies.get(ACCESS_COOKIE)
    if cookie:
        return cookie, "cookie"
    return None, "none"


def _enforce_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or cookie != header:
        raise PermissionDenied("CSRF token missing or invalid.", code="csrf_failed")


def get_optional_user(request: Request, db: DB) -> User | None:
    token, source = _extract_token(request)
    if token is None:
        return None
    payload = decode_access_token(token)
    if source == "cookie":
        _enforce_csrf(request)
    session = SessionRepository(db).get_by_public_id(payload.get("sid", ""))
    if session is None or session.revoked_at is not None or session.expires_at < utcnow():
        raise AuthenticationError("Session is no longer valid.", code="session_revoked")
    user = UserRepository(db).get_by_public_id(payload.get("sub", ""))
    if user is None or user.deleted_at is not None or user.id != session.user_id:
        raise AuthenticationError("User not found.", code="user_not_found")
    if user.status in {UserStatus.SUSPENDED, UserStatus.INACTIVE}:
        raise PermissionDenied("This account is suspended.", code="account_suspended")
    request.state.session_public_id = session.public_id
    request.state.user = user
    return user


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise AuthenticationError("Authentication required.", code="unauthenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_platform_admin(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        raise PermissionDenied("Platform administrator access required.", code="platform_admin_required")
    return user


PlatformAdmin = Annotated[User, Depends(require_platform_admin)]


@dataclass
class TenantContext:
    user: User
    organization: Organization
    membership: OrganizationMembership | None
    permissions: set[str] = field(default_factory=set)
    is_platform_admin: bool = False

    @property
    def role_code(self) -> str | None:
        return self.membership.role.code if self.membership else ("platform_super_admin" if self.is_platform_admin else None)

    @property
    def branch_id(self) -> int | None:
        return self.membership.branch_id if self.membership else None

    def has(self, permission: str) -> bool:
        return self.is_platform_admin or permission in self.permissions

    def require(self, *permissions: str) -> None:
        missing = [p for p in permissions if not self.has(p)]
        if missing:
            raise PermissionDenied(f"Missing permission: {', '.join(missing)}", code="permission_denied")


def resolve_tenant(
    request: Request,
    db: Session,
    user: User,
    organization_public_id: str | None,
    *,
    allow_inactive_org: bool = False,
) -> TenantContext:
    orgs = OrganizationRepository(db)
    memberships = MembershipRepository(db)
    org: Organization | None = None
    if organization_public_id:
        org = orgs.get_by_public_id(organization_public_id)
        if org is None or org.deleted_at is not None:
            raise NotFoundError("Organization not found.")
    else:
        active = [m for m in memberships.list_for_user(user.id) if m.organization.deleted_at is None]
        if len(active) == 1:
            org = active[0].organization
        elif not active:
            raise PermissionDenied("You are not a member of any organization.", code="no_membership")
        else:
            raise ValidationFailed(
                f"Select an organization: send the {ORG_HEADER} header.", code="organization_required"
            )

    membership = memberships.get_for_user_in_org(user.id, org.id)
    if membership is None:
        if not user.is_platform_admin:
            raise PermissionDenied("You do not belong to this organization.", code="not_a_member")
        record_audit(
            db, action="platform.impersonate", actor=user, organization_id=org.id, entity_type="organization",
            entity_id=org.public_id, purpose=f"{request.method} {request.url.path}", meta=get_request_meta(request),
        )
    if org.status != OrganizationStatus.ACTIVE and not user.is_platform_admin and not allow_inactive_org:
        raise PermissionDenied("This organization is not active.", code="organization_inactive")

    permissions = set(PERMISSIONS) if user.is_platform_admin else {p.code for p in membership.role.permissions}  # type: ignore[union-attr]
    ctx = TenantContext(
        user=user, organization=org, membership=membership, permissions=permissions, is_platform_admin=user.is_platform_admin
    )
    request.state.tenant = ctx
    return ctx


def get_tenant_context(
    request: Request,
    db: DB,
    user: CurrentUser,
    x_organization_id: Annotated[str | None, Header(alias=ORG_HEADER)] = None,
) -> TenantContext:
    """Tenant from the ``X-Organization-Id`` header, the ``organization_id`` path parameter, or the sole membership."""
    org_id = request.path_params.get("organization_id") or x_organization_id
    return resolve_tenant(request, db, user, org_id)


Tenant = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(*permissions: str):
    def dependency(ctx: Tenant) -> TenantContext:
        ctx.require(*permissions)
        return ctx

    return dependency
