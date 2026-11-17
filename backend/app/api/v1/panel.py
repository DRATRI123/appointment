"""Embedded admin panel: sign-in inside a clinic's own app (see app/services/panel_service.py).

The tokens are returned in the body only and never set as cookies: they stay inside the frame (the website keeps them
in that frame's session storage), so a panel sign-in never replaces or ends the person's ordinary sign-in in the same
browser, and the clinic's app never sees them.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, Meta
from app.core.exceptions import AuthenticationError, PermissionDenied
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRead
from app.security.rate_limit import limiter
from app.services import panel_service
from app.services.audit_service import record_audit
from app.services.auth_service import AuthResult, AuthService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/panel", tags=["embedded panel"])

ORIGIN = re.compile(r"^https?://[a-z0-9.-]+(:\d{1,5})?$")


class PanelPolicy(BaseModel):
    enabled: bool
    allowed_origins: list[str]
    organization_name: str


class PanelLogin(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)
    parent_origin: str | None = Field(default=None, max_length=300, description="The app showing the panel (for the audit log)")


class PanelMfa(BaseModel):
    mfa_token: str = Field(max_length=2000)
    code: str = Field(max_length=32)


class PanelRefresh(BaseModel):
    refresh_token: str = Field(max_length=500)


class PanelTokens(TokenResponse):
    organization_id: str


def _org(db, slug: str):
    return OrganizationService(db).get_by_slug_public(slug)


def _tokens(result: AuthResult, org) -> PanelTokens:
    return PanelTokens(access_token=result.access_token, refresh_token=result.refresh_token, expires_in=result.expires_in,
                       user=UserRead.model_validate(result.user), organization_id=org.public_id)


@router.get("/{slug}/policy", response_model=PanelPolicy, summary="Public: is the panel on, and which apps may show it")
def panel_policy(slug: str, db: DB, response: Response) -> PanelPolicy:
    """Read by the website to set ``frame-ancestors`` on /panel/<clinic>. The addresses are not secret (browsers see
    them in that header anyway); they are listed only while the panel is on."""
    org = _org(db, slug)
    pol = panel_service.policy(db, org)
    response.headers["Cache-Control"] = "public, max-age=60"
    on = panel_service.is_open(pol)
    return PanelPolicy(enabled=on, allowed_origins=pol["allowed_origins"] if on else [], organization_name=org.name)


@router.post("/{slug}/login", response_model=PanelTokens, summary="Sign in inside the clinic's embedded panel")
@limiter.limit("10/minute")
def panel_login(request: Request, response: Response, slug: str, payload: PanelLogin, db: DB, meta: Meta) -> PanelTokens:
    org = _org(db, slug)
    panel_service.require_open(db, org)
    auth = AuthService(db, meta)
    user = auth.check_password_login(email=payload.email, password=payload.password)
    parent = (payload.parent_origin or "").strip().lower().rstrip("/")
    parent = parent if ORIGIN.fullmatch(parent) else None
    try:
        membership = panel_service.member_with_permission(db, org, user)
    except PermissionDenied:
        record_audit(db, action="auth.panel_login_refused", actor=user, organization_id=org.id, entity_type="user",
                     entity_id=user.public_id, after={"reason": "no_permission", "parent_origin": parent}, meta=meta)
        raise PermissionDenied("This account cannot open the admin panel here. Ask the clinic owner for the permission "
                               "\"Open the admin panel inside the clinic's own app\".", code="panel_not_allowed", persist=True) from None
    from app.services.mfa_service import ADMIN_ROLES

    if user.mfa_enabled_at is None and membership.role is not None and membership.role.code in ADMIN_ROLES:
        row = OrganizationService(db).orgs.get_setting(org.id, "security", "require_admin_mfa")
        if row is not None and (row.value or {}).get("v") is True:
            raise PermissionDenied("This clinic requires two-step sign-in for administrators. Turn it on in the appointment app "
                                   "(Profile & security), then sign in here.", code="mfa_setup_required")
    record_audit(db, action="auth.panel_login", actor=user, organization_id=org.id, entity_type="user", entity_id=user.public_id,
                 after={"parent_origin": parent, "in_allowed_list": parent in panel_service.policy(db, org)["allowed_origins"] if parent else None},
                 meta=meta)
    return _tokens(auth.issue_panel_session(user, org), org)  # accounts with two-step sign-in get mfa_required first


@router.post("/{slug}/mfa", response_model=PanelTokens, summary="Second sign-in step inside the embedded panel")
@limiter.limit("10/minute")
def panel_mfa(request: Request, response: Response, slug: str, payload: PanelMfa, db: DB, meta: Meta) -> PanelTokens:
    from app.services.mfa_service import MFAService

    org = _org(db, slug)
    panel_service.require_open(db, org)
    result = MFAService(db, meta).complete_sign_in(payload.mfa_token, payload.code, panel_organization=org)
    panel_service.member_with_permission(db, org, result.user)
    return _tokens(result, org)


@router.post("/{slug}/refresh", response_model=PanelTokens, summary="New access token for an embedded-panel sign-in")
@limiter.limit("30/minute")
def panel_refresh(request: Request, response: Response, slug: str, payload: PanelRefresh, db: DB, meta: Meta) -> PanelTokens:
    org = _org(db, slug)
    panel_service.require_open(db, org)
    result = AuthService(db, meta).refresh(payload.refresh_token, panel_organization_id=org.id)
    panel_service.member_with_permission(db, org, result.user)
    return _tokens(result, org)


@router.post("/logout", status_code=204, summary="Sign out of the embedded panel (the ordinary sign-in is not touched)")
def panel_logout(payload: PanelRefresh, db: DB, meta: Meta) -> Response:
    from app.repositories.users import SessionRepository
    from app.security.tokens import hash_token

    session = SessionRepository(db).get_by_token_hash(hash_token(payload.refresh_token))
    if session is None or session.panel_organization_id is None:
        raise AuthenticationError("Invalid refresh token.", code="refresh_invalid")
    AuthService(db, meta).logout(None, payload.refresh_token)
    return Response(status_code=204)
