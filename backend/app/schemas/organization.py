from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field

from app.schemas.common import APIModel


class OrganizationCreate(APIModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    business_type: str | None = Field(default=None, max_length=64)
    legal_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    description: str | None = None
    address: dict[str, Any] | None = None
    timezone: str = "Asia/Kolkata"
    currency: str = Field(default="INR", min_length=3, max_length=3)
    locale: str = "en-IN"


class OrganizationUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=512)
    description: str | None = None
    address: dict[str, Any] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, max_length=16)


class OrganizationRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    slug: str
    code: str
    name: str
    legal_name: str | None
    business_type: str | None
    email: str | None
    phone: str | None
    website: str | None
    logo_url: str | None
    description: str | None
    address: dict[str, Any] | None
    timezone: str
    currency: str
    locale: str
    status: str
    created_at: datetime
    updated_at: datetime


class OrganizationStatusUpdate(APIModel):
    status: str = Field(pattern=r"^(pending|active|suspended|closed)$")
    reason: str | None = Field(default=None, max_length=500)


class OrganizationSettingsRead(APIModel):
    namespace: str
    values: dict[str, Any]


class OrganizationSettingsUpdate(APIModel):
    values: dict[str, Any]


class DomainCreate(APIModel):
    domain: str = Field(min_length=3, max_length=255, pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$")
    is_primary: bool = False


class DomainRead(APIModel):
    id: int
    domain: str
    is_primary: bool
    is_verified: bool
    verification_token: str | None
    verified_at: datetime | None
    created_at: datetime
