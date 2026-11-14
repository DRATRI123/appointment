"""Shared FastAPI dependencies: database, current user, tenant context, permission guards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.enums import OrganizationStatus, UserStatus
from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDenied, RateLimited, ValidationFailed
from app.core.time import utcnow
from app.models import Organization, OrganizationMembership, User
from app.repositories.organizations import MembershipRepository, OrganizationRepository
from app.repositories.users import SessionRepository, UserRepository
from app.security.client_ip import client_ip
from app.security.permissions import PERMISSIONS
from app.security.tokens import decode_access_token
from app.services.audit_service import RequestMeta, record_audit

# scope="function": the session commits after the endpoint returns but BEFORE the response is sent. With the default
# ("request") FastAPI sends the response first and commits afterwards, so a client could be told "booked" for a booking
# whose commit then failed, and its very next request could miss what it had just created.
DB = Annotated[Session, Depends(get_db, scope="function")]
AppSettings = Annotated[Settings, Depends(get_settings)]

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
ORG_HEADER = "X-Organization-Id"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_request_meta(request: Request) -> RequestMeta:
    ip = client_ip(request)
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


def _authenticate_api_key(request: Request, db: Session, raw: str) -> User:
    """API key principal: the key's creator, limited later (resolve_tenant) to the key's organization and scopes."""
    from app.models import APIKey
    from app.security import api_keys as ak

    settings = get_settings()
    key = db.scalar(select(APIKey).where(APIKey.key_hash == ak.hash_key(raw)))
    now = utcnow()
    if key is None or not key.is_active or key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        raise AuthenticationError("Invalid, expired or revoked API key.", code="invalid_api_key")
    request.state.api_key = key
    request.state.api_key_savepoint = db.begin_nested()
    if not ak.path_allowed(request.url.path, settings.api_v1_prefix):
        raise PermissionDenied("API keys cannot be used on this endpoint.", code="api_key_not_allowed")
    if not ak.ip_allowed(get_request_meta(request).ip_address, key.allowed_ips):
        raise PermissionDenied("This API key is not allowed from your IP address.", code="ip_not_allowed")
    configured = (key.rate_limit or "").split("/")[0]
    limit = int(configured) if configured.isdigit() else settings.api_key_default_rate_limit
    allowed, retry_after = ak.limiter.hit(key.id, limit)
    if not allowed:
        request.state.api_key_rate_limited = True
        raise RateLimited(f"Rate limit of {limit} requests per minute exceeded for this API key.", headers={"Retry-After": str(retry_after)})
    user = db.get(User, key.created_by_user_id) if key.created_by_user_id else None
    if user is None or user.deleted_at is not None or user.status in {UserStatus.SUSPENDED, UserStatus.INACTIVE}:
        raise AuthenticationError("The person who created this API key no longer has access.", code="api_key_owner_removed")
    if key.last_used_at is None or (now - key.last_used_at).total_seconds() > 60:
        key.last_used_at = now
    request.state.user = user
    return user


def track_api_key_usage(request: Request, db: DB):
    """Counts API-key requests in the request's own session (SQLite allows one writer, so a second session would wait
    on this one). Failed calls are counted too: the request's work, which runs inside a SAVEPOINT opened when the key
    was recognised, is rolled back, and only the usage row is committed."""
    from app.services.developer_service import record_usage

    try:
        yield
    except Exception as exc:
        key = getattr(request.state, "api_key", None)
        if key is not None:
            savepoint = getattr(request.state, "api_key_savepoint", None)
            if savepoint is not None and savepoint.is_active:
                savepoint.rollback()  # undo only this request's work
            try:
                record_usage(db, key.id, key.organization_id, int(getattr(exc, "status_code", 500)), bool(getattr(request.state, "api_key_rate_limited", False)))
                db.commit()
            except Exception:  # noqa: BLE001 - never mask the original error
                db.rollback()
        raise
    else:
        key = getattr(request.state, "api_key", None)
        if key is not None:
            record_usage(db, key.id, key.organization_id, 200, False)


def get_optional_user(request: Request, db: DB, _usage: Annotated[None, Depends(track_api_key_usage, scope="function")] = None) -> User | None:
    from app.security.api_keys import looks_like_key

    token, source = _extract_token(request)
    header_key = request.headers.get("x-api-key")
    if header_key or (source == "header" and looks_like_key(token)):
        return _authenticate_api_key(request, db, (header_key or token or "").strip())
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
    api_key = getattr(request.state, "api_key", None)
    if api_key is not None:
        return _resolve_api_key_tenant(request, db, user, api_key, organization_public_id)
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


def _resolve_api_key_tenant(request: Request, db: Session, user: User, key, organization_public_id: str | None) -> TenantContext:
    from app.security.api_keys import API_SCOPES

    org = db.get(Organization, key.organization_id)
    if org is None or org.deleted_at is not None:
        raise NotFoundError("Organization not found.")
    if organization_public_id and organization_public_id != org.public_id:
        raise PermissionDenied("This API key belongs to another organization.", code="wrong_organization")
    if org.status != OrganizationStatus.ACTIVE:
        raise PermissionDenied("This organization is not active.", code="organization_inactive")
    membership = MembershipRepository(db).get_for_user_in_org(user.id, org.id)
    if membership is None:  # platform admins get no special powers through a key
        raise AuthenticationError("The person who created this API key no longer has access.", code="api_key_owner_removed")
    role_permissions = {p.code for p in membership.role.permissions}
    permissions = set(key.scopes or []) & role_permissions & set(API_SCOPES)
    ctx = TenantContext(user=user, organization=org, membership=membership, permissions=permissions, is_platform_admin=False)
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
