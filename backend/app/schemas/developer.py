from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class ApiKeyCreate(APIModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None
    allowed_ips: list[str] = Field(default_factory=list, max_length=20)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1200)

    @field_validator("allowed_ips")
    @classmethod
    def _ips(cls, v: list[str]) -> list[str]:
        from app.security.api_keys import validate_cidrs

        return validate_cidrs(v)


class ApiKeyRead(APIModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    allowed_ips: list[str]
    rate_limit_per_minute: int
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    is_active: bool
    created_by_name: str | None
    created_at: datetime
    requests_30d: int


class ApiKeyCreated(ApiKeyRead):
    key: str  # shown once


class ScopeInfo(APIModel):
    code: str
    description: str
    you_have_it: bool


class WebhookCreate(APIModel):
    name: str = Field(min_length=2, max_length=120)
    url: str = Field(min_length=8, max_length=1024)
    events: list[str] = Field(min_length=1)
    is_active: bool = True


class WebhookUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=1024)
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookRead(APIModel):
    id: str
    name: str
    url: str
    events: list[str]
    is_active: bool
    api_version: str
    failure_count: int
    disabled_at: datetime | None
    created_at: datetime
    delivered_7d: int
    failed_7d: int


class WebhookCreated(WebhookRead):
    secret: str  # shown once


class DeliveryRead(APIModel):
    id: str
    event_id: str
    event: str
    status: str
    attempts: int
    response_status: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    created_at: datetime


class DeliveryDetail(DeliveryRead):
    payload: dict[str, Any]
    response_body: str | None


class EventInfo(APIModel):
    name: str
    description: str
    sample: dict[str, Any]


class UsageDay(APIModel):
    day: date
    requests: int
    client_errors: int
    server_errors: int
    rate_limited: int


class OrgApiUsage(APIModel):
    organization_id: str
    organization_name: str
    active_keys: int
    requests: int
    errors: int
    rate_limited: int
    endpoints: int
    endpoints_disabled: int
    deliveries_ok: int
    deliveries_failed: int
