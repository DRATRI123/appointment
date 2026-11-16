from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import DB, CurrentUser, TenantContext, get_tenant_context
from app.schemas.user import MeResponse, UserRead, UserUpdate
from app.services.user_service import build_me_response, update_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse, summary="Current user, memberships and permissions")
def me(db: DB, user: CurrentUser) -> MeResponse:
    return build_me_response(db, user)


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
