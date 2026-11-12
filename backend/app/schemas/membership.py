from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.user import UserRead


class MemberInvite(APIModel):
    identifier: str = Field(min_length=3, max_length=255, description="Mobile number or email")
    full_name: str = Field(min_length=2, max_length=160)
    role_code: str = Field(min_length=2, max_length=48)
    branch_id: str | None = None


class MemberUpdate(APIModel):
    role_code: str | None = Field(default=None, min_length=2, max_length=48)
    branch_id: str | None = None
    clear_branch: bool = False
    status: str | None = Field(default=None, pattern=r"^(active|suspended)$")


class MemberRead(APIModel):
    id: str
    user: UserRead
    role_code: str
    role_name: str
    branch_id: str | None
    status: str
    invited_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime
