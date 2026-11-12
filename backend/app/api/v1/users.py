from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.schemas.user import MeResponse, UserRead, UserUpdate
from app.services.user_service import build_me_response, update_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse, summary="Current user, memberships and permissions")
def me(db: DB, user: CurrentUser) -> MeResponse:
    return build_me_response(db, user)


@router.patch("/me", response_model=UserRead, summary="Update own profile")
def patch_me(payload: UserUpdate, db: DB, user: CurrentUser) -> UserRead:
    return UserRead.model_validate(update_me(db, user, payload))
