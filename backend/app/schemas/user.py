from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field

from app.schemas.common import APIModel


class UserRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    full_name: str
    email: str | None
    mobile: str | None
    avatar_url: str | None
    status: str
    is_platform_admin: bool
    email_verified_at: datetime | None
    mobile_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    avatar_url: str | None = Field(default=None, max_length=512)
    preferences: dict[str, Any] | None = None


class OrganizationSummary(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    name: str
    slug: str
    logo_url: str | None
    status: str
    timezone: str
    currency: str


class MembershipSummary(APIModel):
    id: str
    organization: OrganizationSummary
    role_code: str
    role_name: str
    branch_id: str | None
    status: str
    permissions: list[str]


class MeResponse(APIModel):
    user: UserRead
    memberships: list[MembershipSummary]
    is_platform_admin: bool
