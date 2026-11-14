from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel

LIMIT_KEYS = ("branches", "professionals", "staff", "appointments_per_month")


class Plan(APIModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,47}$")
    name: str = Field(min_length=2, max_length=96)
    price_paise: int = Field(ge=0, le=100_000_000)
    billing_cycle: str = Field(default="monthly", pattern=r"^(monthly|quarterly|yearly)$")
    limits: dict[str, int | None] = Field(default_factory=dict, description="branches, professionals, staff, appointments_per_month; null = unlimited")
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @field_validator("limits")
    @classmethod
    def _limits(cls, v: dict[str, int | None]) -> dict[str, int | None]:
        unknown = set(v) - set(LIMIT_KEYS)
        if unknown:
            raise ValueError(f"Unknown limits: {', '.join(sorted(unknown))}")
        if any(x is not None and x < 0 for x in v.values()):
            raise ValueError("Limits cannot be negative.")
        return v


class PlatformSettings(APIModel):
    platform_name: str = Field(default="Appointment Platform", min_length=2, max_length=96)
    support_email: str = Field(default="", max_length=255)
    allow_organization_signup: bool = True
    default_plan_code: str | None = None
    default_trial_days: int = Field(default=14, ge=0, le=365)
    announcement: str = Field(default="", max_length=500)
    announcement_level: str = Field(default="info", pattern=r"^(info|warning)$")


class PublicPlatform(APIModel):
    platform_name: str
    support_email: str
    allow_organization_signup: bool
    announcement: str
    announcement_level: str


class SubscriptionRead(APIModel):
    id: str
    plan_code: str
    plan_name: str
    status: str
    price_paise: int
    billing_cycle: str
    limits: dict[str, Any]
    starts_at: datetime | None
    ends_at: datetime | None
    trial_ends_at: datetime | None
    cancelled_at: datetime | None
    notes: str | None
    created_at: datetime


class SubscriptionUpdate(APIModel):
    plan_code: str
    status: str = Field(pattern=r"^(trial|active|past_due|cancelled|expired)$")
    trial_ends_at: datetime | None = None
    ends_at: datetime | None = None
    price_paise: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class Usage(APIModel):
    branches: int
    professionals: int
    staff: int
    customers: int
    appointments_this_month: int
    appointments_30d: int
    verified_receipts_30d_paise: int


class OrgSummary(APIModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: datetime
    subscription: SubscriptionRead | None
    usage: Usage
    over_limit: list[str]


class OrgOverview(OrgSummary):
    email: str | None
    phone: str | None
    timezone: str
    owner_name: str | None
    owner_contact: str | None
    recent_activity: list[dict[str, Any]]


class PlatformDayPoint(APIModel):
    date: date
    appointments: int
    signups: int


class PlatformDashboard(APIModel):
    days: int
    totals: dict[str, int]
    series: list[PlatformDayPoint]
    top_organizations: list[dict[str, Any]]
    plans: list[dict[str, Any]]
