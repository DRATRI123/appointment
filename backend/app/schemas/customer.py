from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel

GENDERS = r"^(male|female|other|undisclosed)$"


class CustomerBase(APIModel):
    full_name: str = Field(min_length=2, max_length=160)
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern=GENDERS)
    address: dict[str, Any] | None = None
    profile_photo_url: str | None = Field(default=None, max_length=512)
    blood_group: str | None = Field(default=None, max_length=8)
    communication_preferences: dict[str, Any] | None = None
    consent: dict[str, Any] | None = None
    tags: list[str] | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern=GENDERS)
    address: dict[str, Any] | None = None
    profile_photo_url: str | None = Field(default=None, max_length=512)
    blood_group: str | None = Field(default=None, max_length=8)
    communication_preferences: dict[str, Any] | None = None
    consent: dict[str, Any] | None = None
    tags: list[str] | None = None
    saved_professional_ids: list[str] | None = None
    saved_branch_ids: list[str] | None = None


class CustomerStats(APIModel):
    total_appointments: int = 0
    upcoming_appointments: int = 0
    completed_appointments: int = 0
    cancelled_appointments: int = 0
    no_shows: int = 0
    total_paid_paise: int = 0
    last_visit_at: datetime | None = None
    next_appointment_at: datetime | None = None


class CustomerRead(CustomerBase):
    id: str
    customer_code: str | None
    user_id: str | None
    is_guest: bool
    source: str | None
    registered_at: datetime | None
    last_visit_at: datetime | None
    saved_professional_ids: list[str] = Field(default_factory=list)
    saved_branch_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    stats: CustomerStats | None = None
    dependents_count: int = 0


class DependentBase(APIModel):
    full_name: str = Field(min_length=2, max_length=160)
    relationship_label: str | None = Field(default=None, max_length=48)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern=GENDERS)
    mobile: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)


class DependentCreate(DependentBase):
    pass


class DependentUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    relationship_label: str | None = Field(default=None, max_length=48)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern=GENDERS)
    mobile: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)


class DependentRead(DependentBase):
    id: str
    customer_id: str
    created_at: datetime


class NoteCreate(APIModel):
    body: str = Field(min_length=1, max_length=20000)
    note_type: str = Field(default="general", pattern=r"^(general|clinical|allergy|medication|follow_up|admin)$")
    appointment_id: str | None = None
    is_sensitive: bool = True


class NoteRead(APIModel):
    id: str
    note_type: str
    body: str
    is_sensitive: bool
    appointment_id: str | None
    author_name: str | None
    created_at: datetime
    updated_at: datetime


class DocumentRead(APIModel):
    id: str
    title: str
    document_type: str
    mime_type: str
    size_bytes: int
    is_sensitive: bool
    appointment_id: str | None
    uploaded_by_name: str | None
    retention_until: date | None
    created_at: datetime


class CustomerExportRow(APIModel):
    customer_code: str | None
    full_name: str
    mobile: str | None
    email: str | None
    gender: str | None
    date_of_birth: date | None
    tags: str
    is_guest: bool
    registered_at: datetime | None
    last_visit_at: datetime | None
    total_appointments: int


class SelfProfileUpdate(APIModel):
    """What a customer may edit about their own record in an organization."""

    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern=GENDERS)
    address: dict[str, Any] | None = None
    blood_group: str | None = Field(default=None, max_length=8)
    communication_preferences: dict[str, Any] | None = None
    consent: dict[str, Any] | None = None
    saved_professional_ids: list[str] | None = None
    saved_branch_ids: list[str] | None = None
