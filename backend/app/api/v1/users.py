from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser, Meta, TenantContext, get_tenant_context
from app.schemas.user import MeResponse, UserRead, UserUpdate
from app.security.rate_limit import limiter
from app.services.audit_service import record_audit
from app.services.user_service import build_me_response, update_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse, summary="Current user, memberships and permissions")
def me(request: Request, db: DB, user: CurrentUser) -> MeResponse:
    return build_me_response(db, user, panel_organization_id=getattr(request.state, "panel_organization_id", None))


@router.patch("/me", response_model=UserRead, summary="Update own profile")
def patch_me(payload: UserUpdate, db: DB, user: CurrentUser) -> UserRead:
    return UserRead.model_validate(update_me(db, user, payload))


@router.get("/me/privacy", summary="This clinic's privacy rules for me: screen lock, watermark, printing, masking")
def my_privacy(request: Request, db: DB, ctx: Annotated[TenantContext, Depends(get_tenant_context)]) -> dict:
    """Read by the website to show the lock screen, watermark and print notice. The API enforces the rules itself."""
    from app.services.privacy_service import lock_minutes, policy

    pol = policy(db, ctx.organization)
    sid = getattr(request.state, "session_public_id", "") or ""
    return {
        "lock_after_minutes": lock_minutes(pol, ctx.role_code),
        "lock_when_hidden": pol["lock_when_hidden"],
        "watermark_enabled": pol["watermark_enabled"],
        "watermark_opacity": pol["watermark_opacity"],
        "print_policy": pol["print_policy"],
        "reauth_window_minutes": pol["reauth_window_minutes"],
        "mask_contact_details": pol["mask_contact_details"],
        # For the watermark: who and which session, without personal data (no name, email or number).
        "user_ref": "U-" + ctx.user.public_id.replace("-", "")[:8].upper(),
        "session_ref": "S-" + sid.replace("-", "")[:6].upper(),
        "organization_ref": ctx.organization.slug,
        "has_password": bool(ctx.user.password_hash),
        "has_authenticator": ctx.user.mfa_enabled_at is not None,
    }


class PrintAttempt(BaseModel):
    screen: str = Field(default="", max_length=200)


@router.post("/me/privacy/print-attempt", summary="Record that a staff screen was printed (or printing was tried)")
@limiter.limit("30/minute")
def print_attempt(request: Request, response: Response, payload: PrintAttempt, db: DB, ctx: Annotated[TenantContext, Depends(get_tenant_context)], meta: Meta) -> dict:
    """The page path only (never query strings, which could carry search terms)."""
    from app.services.privacy_service import policy

    screen = payload.screen.split("?", 1)[0].split("#", 1)[0]
    record_audit(db, action="privacy.print_attempt", actor=ctx.user, organization_id=ctx.organization.id, entity_type="screen",
                 entity_id=screen[:120] or None, after={"policy": policy(db, ctx.organization)["print_policy"]}, meta=meta)
    return {"detail": "Recorded."}
