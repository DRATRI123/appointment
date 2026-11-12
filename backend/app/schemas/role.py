from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel


class PermissionRead(APIModel):
    code: str
    module: str
    description: str | None


class RoleRead(APIModel):
    id: int
    code: str
    name: str
    description: str | None
    is_system: bool
    scope: str
    is_custom: bool
    permissions: list[str]


class RoleCreate(APIModel):
    code: str = Field(min_length=2, max_length=48, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=96)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    clone_from: str | None = Field(default=None, description="System role code to copy permissions from")


class RoleUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=96)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] | None = None
