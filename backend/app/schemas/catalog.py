"""Schemas for branches, professionals, service categories, services and packages."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field, field_validator

from app.schemas.common import APIModel

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _validate_hours(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    for day, windows in value.items():
        if day not in WEEKDAYS:
            raise ValueError(f"Unknown weekday '{day}'. Use {', '.join(WEEKDAYS)}.")
        if not isinstance(windows, list):
            raise ValueError(f"{day}: expected a list of [start, end] windows")
        for window in windows:
            if not (isinstance(window, list) and len(window) == 2 and all(isinstance(t, str) for t in window)):
                raise ValueError(f"{day}: each window must be ['HH:MM', 'HH:MM']")
            start, end = window
            if not (len(start) == 5 and len(end) == 5 and start < end):
                raise ValueError(f"{day}: window {start}-{end} is invalid")
    return value


# ------------------------------------------------------------------ branches
class BranchBase(APIModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: dict[str, Any] | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = Field(default=None, max_length=64)
    business_hours: dict[str, Any] | None = None
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    is_active: bool = True
    is_default: bool = False

    @field_validator("business_hours")
    @classmethod
    def _hours(cls, v):
        return _validate_hours(v)


class BranchCreate(BranchBase):
    slug: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")


class BranchUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: dict[str, Any] | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = Field(default=None, max_length=64)
    business_hours: dict[str, Any] | None = None
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None
    is_default: bool | None = None

    @field_validator("business_hours")
    @classmethod
    def _hours(cls, v):
        return _validate_hours(v)


class BranchRead(BranchBase):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    slug: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------- categories
class CategoryBase(APIModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    parent_id: str | None = None


class CategoryUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None
    is_active: bool | None = None
    parent_id: str | None = None


class CategoryRead(CategoryBase):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    slug: str
    parent_id: str | None = None
    service_count: int = 0


# ----------------------------------------------------------------- services
class ServicePricingInput(APIModel):
    branch_id: str
    price_paise: int | None = Field(default=None, ge=0)
    discounted_price_paise: int | None = Field(default=None, ge=0)
    advance_amount_paise: int | None = Field(default=None, ge=0)
    is_available: bool = True


class ServicePricingRead(ServicePricingInput):
    branch_name: str | None = None


class ServiceBase(APIModel):
    name: str = Field(min_length=2, max_length=160)
    kind: str = Field(default="standard", pattern=r"^(standard|addon|follow_up)$")
    short_description: str | None = Field(default=None, max_length=255)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    duration_minutes: int = Field(default=15, ge=5, le=720)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    consultation_mode: str = Field(default="in_person", pattern=r"^(in_person|online|both)$")
    price_paise: int = Field(default=0, ge=0)
    discounted_price_paise: int | None = Field(default=None, ge=0)
    payment_mode: str = Field(default="full_advance", pattern=r"^(free|full_advance|partial_advance|pay_at_clinic|optional_advance)$")
    advance_amount_paise: int | None = Field(default=None, ge=0)
    advance_percent: int | None = Field(default=None, ge=1, le=100)
    tax_percent: int = Field(default=0, ge=0, le=100)
    min_notice_minutes: int | None = Field(default=None, ge=0)
    max_advance_days: int | None = Field(default=None, ge=1, le=365)
    cancellation_policy: dict[str, Any] | None = None
    booking_rules: dict[str, Any] | None = None
    instructions: str | None = None
    follow_up_within_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool = True
    is_bookable_online: bool = True
    sort_order: int = 0


class ServiceCreate(ServiceBase):
    slug: str | None = Field(default=None, min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9-]*$")
    category_id: str | None = None
    follow_up_service_id: str | None = None
    pricing: list[ServicePricingInput] = Field(default_factory=list)
    professional_ids: list[str] = Field(default_factory=list)


class ServiceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    kind: str | None = Field(default=None, pattern=r"^(standard|addon|follow_up)$")
    category_id: str | None = None
    clear_category: bool = False
    short_description: str | None = Field(default=None, max_length=255)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=512)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    consultation_mode: str | None = Field(default=None, pattern=r"^(in_person|online|both)$")
    price_paise: int | None = Field(default=None, ge=0)
    discounted_price_paise: int | None = Field(default=None, ge=0)
    payment_mode: str | None = Field(default=None, pattern=r"^(free|full_advance|partial_advance|pay_at_clinic|optional_advance)$")
    advance_amount_paise: int | None = Field(default=None, ge=0)
    advance_percent: int | None = Field(default=None, ge=1, le=100)
    tax_percent: int | None = Field(default=None, ge=0, le=100)
    min_notice_minutes: int | None = Field(default=None, ge=0)
    max_advance_days: int | None = Field(default=None, ge=1, le=365)
    cancellation_policy: dict[str, Any] | None = None
    booking_rules: dict[str, Any] | None = None
    instructions: str | None = None
    follow_up_service_id: str | None = None
    follow_up_within_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None
    is_bookable_online: bool | None = None
    sort_order: int | None = None
    pricing: list[ServicePricingInput] | None = None
    professional_ids: list[str] | None = None


class ServiceRead(ServiceBase):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    slug: str
    currency: str
    category_id: str | None = None
    category_name: str | None = None
    follow_up_service_id: str | None = None
    pricing: list[ServicePricingRead] = Field(default_factory=list)
    professional_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- packages
class PackageItemInput(APIModel):
    service_id: str
    quantity: int = Field(default=1, ge=1, le=100)


class PackageCreate(APIModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    price_paise: int = Field(ge=0)
    validity_days: int | None = Field(default=None, ge=1, le=3650)
    is_active: bool = True
    items: list[PackageItemInput] = Field(min_length=1)


class PackageUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    price_paise: int | None = Field(default=None, ge=0)
    validity_days: int | None = Field(default=None, ge=1, le=3650)
    is_active: bool | None = None
    items: list[PackageItemInput] | None = None


class PackageItemRead(PackageItemInput):
    service_name: str | None = None


class PackageRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    name: str
    description: str | None
    price_paise: int
    validity_days: int | None
    is_active: bool
    items: list[PackageItemRead] = Field(default_factory=list)
    created_at: datetime


# ------------------------------------------------------------ professionals
class ProfessionalBranchInput(APIModel):
    branch_id: str
    fee_paise: int | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    room_label: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class ProfessionalBranchRead(ProfessionalBranchInput):
    branch_name: str | None = None


class ProfessionalServiceInput(APIModel):
    service_id: str
    branch_id: str | None = None
    fee_override_paise: int | None = Field(default=None, ge=0)
    duration_override_minutes: int | None = Field(default=None, ge=5, le=720)
    is_active: bool = True


class ProfessionalServiceRead(ProfessionalServiceInput):
    service_name: str | None = None


class ProfessionalBase(APIModel):
    display_name: str = Field(min_length=2, max_length=160)
    title: str | None = Field(default=None, max_length=32)
    profile_photo_url: str | None = Field(default=None, max_length=512)
    qualification: str | None = Field(default=None, max_length=255)
    specialization: str | None = Field(default=None, max_length=160)
    experience_years: int | None = Field(default=None, ge=0, le=80)
    registration_number: str | None = Field(default=None, max_length=96)
    registration_council: str | None = Field(default=None, max_length=160)
    biography: str | None = None
    languages: list[str] | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    consultation_modes: list[str] | None = None
    default_fee_paise: int | None = Field(default=None, ge=0)
    default_duration_minutes: int = Field(default=15, ge=5, le=720)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    slot_capacity: int = Field(default=1, ge=1, le=50)
    is_active: bool = True
    is_bookable_online: bool = True
    sort_order: int = 0


class ProfessionalCreate(ProfessionalBase):
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    user_id: str | None = Field(default=None, description="Link to an existing user account (public id)")
    branches: list[ProfessionalBranchInput] = Field(default_factory=list)
    services: list[ProfessionalServiceInput] = Field(default_factory=list)


class ProfessionalUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    title: str | None = Field(default=None, max_length=32)
    profile_photo_url: str | None = Field(default=None, max_length=512)
    qualification: str | None = Field(default=None, max_length=255)
    specialization: str | None = Field(default=None, max_length=160)
    experience_years: int | None = Field(default=None, ge=0, le=80)
    registration_number: str | None = Field(default=None, max_length=96)
    registration_council: str | None = Field(default=None, max_length=160)
    biography: str | None = None
    languages: list[str] | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    consultation_modes: list[str] | None = None
    default_fee_paise: int | None = Field(default=None, ge=0)
    default_duration_minutes: int | None = Field(default=None, ge=5, le=720)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    slot_capacity: int | None = Field(default=None, ge=1, le=50)
    is_active: bool | None = None
    is_bookable_online: bool | None = None
    sort_order: int | None = None
    user_id: str | None = None
    clear_user: bool = False
    branches: list[ProfessionalBranchInput] | None = None
    services: list[ProfessionalServiceInput] | None = None


class ProfessionalRead(ProfessionalBase):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    slug: str
    user_id: str | None = None
    branches: list[ProfessionalBranchRead] = Field(default_factory=list)
    services: list[ProfessionalServiceRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UploadResponse(APIModel):
    url: str
    key: str
    mime_type: str
    size_bytes: int
