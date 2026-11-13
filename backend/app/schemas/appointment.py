from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field

from app.schemas.common import APIModel


class HoldCreate(APIModel):
    professional_id: str
    branch_id: str
    service_id: str
    start_at: datetime
    session_key: str | None = Field(default=None, max_length=64, description="Client-generated key; defaults to a server key")


class HoldRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    professional_id: str
    branch_id: str
    service_id: str
    start_at: datetime
    end_at: datetime
    expires_at: datetime
    session_key: str
    status: str


class CustomerInput(APIModel):
    full_name: str = Field(min_length=2, max_length=160)
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    customer_id: str | None = Field(default=None, description="Existing customer (staff booking)")


class PriceQuote(APIModel):
    currency: str
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    total_amount_paise: int
    advance_due_paise: int
    payment_mode: str
    breakdown: dict[str, Any]


class AppointmentCreate(APIModel):
    hold_id: str | None = None
    # Direct booking (staff) when no hold is used:
    professional_id: str | None = None
    branch_id: str | None = None
    service_id: str | None = None
    start_at: datetime | None = None
    customer: CustomerInput
    dependent_id: str | None = None
    customer_notes: str | None = Field(default=None, max_length=2000)
    internal_notes: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="online", pattern=r"^(online|reception|walk_in|professional|api)$")
    consultation_mode: str | None = Field(default=None, pattern=r"^(in_person|online)$")
    confirm_without_payment: bool = Field(default=False, description="Staff only: confirm immediately and collect later")
    session_key: str | None = Field(default=None, max_length=64)
    form_answers: dict[str, Any] | None = None
    coupon_code: str | None = Field(default=None, max_length=32)


class RecurringCreate(AppointmentCreate):
    occurrences: int = Field(ge=2, le=26)
    interval_days: int = Field(default=7, ge=1, le=90)


class RescheduleRequest(APIModel):
    hold_id: str | None = None
    professional_id: str | None = None
    start_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class StatusAction(APIModel):
    action: str = Field(pattern=r"^(confirm|check_in|start|complete|no_show|cancel|expire)$")
    reason: str | None = Field(default=None, max_length=500)


class CustomerSummary(APIModel):
    id: str
    full_name: str
    mobile: str | None
    email: str | None
    is_guest: bool


class AppointmentRead(APIModel):
    id: str
    reference: str
    status: str
    source: str
    organization_id: str
    organization_name: str
    organization_slug: str
    branch_id: str
    branch_name: str
    professional_id: str
    professional_name: str
    service_id: str
    service_name: str
    customer: CustomerSummary
    dependent_id: str | None
    start_at: datetime
    end_at: datetime
    timezone: str
    consultation_mode: str
    currency: str
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    total_amount_paise: int
    advance_due_paise: int
    paid_amount_paise: int
    payment_due_at: datetime | None
    customer_notes: str | None
    internal_notes: str | None = None
    meeting_link: str | None
    is_follow_up: bool
    recurrence_group_id: str | None
    parent_appointment_id: str | None
    confirmed_at: datetime | None
    checked_in_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    can_cancel: bool = False
    can_reschedule: bool = False
    access_token: str | None = None


class StatusHistoryRead(APIModel):
    from_status: str | None
    to_status: str
    changed_at: datetime
    reason: str | None
    changed_by: str | None


class AppointmentDetail(AppointmentRead):
    history: list[StatusHistoryRead] = Field(default_factory=list)
    pricing_snapshot: dict[str, Any] | None = None
    form_answers: dict[str, Any] | None = None


class RecurringResult(APIModel):
    recurrence_group_id: str
    created: list[AppointmentRead]
    skipped: list[dict[str, Any]]


class WaitlistCreate(APIModel):
    customer: CustomerInput
    branch_id: str | None = None
    professional_id: str | None = None
    service_id: str | None = None
    preferred_date: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


class WaitlistRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    customer: CustomerSummary
    branch_id: str | None
    professional_id: str | None
    service_id: str | None
    preferred_date: datetime | None
    status: str
    notes: str | None
    created_at: datetime


class CalendarEvent(APIModel):
    id: str
    title: str
    start: datetime
    end: datetime
    status: str
    professional_id: str
    professional_name: str
    branch_id: str
    service_name: str
    customer_name: str
    reference: str
