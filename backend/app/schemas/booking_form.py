from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import APIModel

FIELD_TYPES = ("text", "textarea", "number", "email", "mobile", "dropdown", "radio", "checkbox", "date", "file", "multi_select")
OPTION_TYPES = {"dropdown", "radio", "multi_select"}
OPERATORS = ("equals", "not_equals", "in", "not_in", "is_true", "is_false", "is_empty", "is_not_empty", "gt", "lt")


class FieldOption(APIModel):
    value: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=160)


class FieldCondition(APIModel):
    """Show this field only when ``field`` ``operator`` ``value`` holds."""

    field: str = Field(min_length=1, max_length=64)
    operator: str = Field(pattern="^(" + "|".join(OPERATORS) + ")$")
    value: Any = None


class FieldValidation(APIModel):
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1, le=20000)
    min: float | None = None
    max: float | None = None
    regex: str | None = Field(default=None, max_length=500)
    regex_message: str | None = Field(default=None, max_length=200)
    max_files: int | None = Field(default=None, ge=1, le=10)
    accept: list[str] | None = None  # mime types for file fields
    min_date: str | None = None  # ISO date or "today"
    max_date: str | None = None


class FormFieldInput(APIModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=160)
    field_type: str = Field(pattern="^(" + "|".join(FIELD_TYPES) + ")$")
    placeholder: str | None = Field(default=None, max_length=160)
    help_text: str | None = Field(default=None, max_length=1000)
    is_required: bool = False
    sort_order: int = 0
    options: list[FieldOption] | None = None
    validation: FieldValidation | None = None
    conditions: list[FieldCondition] | None = None
    default_value: Any = None
    is_sensitive: bool = False

    @model_validator(mode="after")
    def _options_required(self):
        if self.field_type in OPTION_TYPES and not self.options:
            raise ValueError(f"{self.field_type} fields need at least one option")
        if self.field_type not in OPTION_TYPES and self.options:
            raise ValueError(f"{self.field_type} fields do not take options")
        return self


class FormFieldRead(FormFieldInput):
    id: str


class BookingFormBase(APIModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    instructions: str | None = Field(default=None, max_length=5000)
    scope: str = Field(default="organization", pattern=r"^(organization|branch|service)$")
    branch_id: str | None = None
    settings: dict[str, Any] | None = None


class BookingFormCreate(BookingFormBase):
    slug: str | None = Field(default=None, min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9-]*$")
    is_template: bool = False
    fields: list[FormFieldInput] = Field(default_factory=list)
    clone_from: str | None = Field(default=None, description="Form or template public id to copy fields from")

    @field_validator("fields")
    @classmethod
    def _unique_keys(cls, v):
        keys = [f.key for f in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Field keys must be unique")
        return v


class BookingFormUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    instructions: str | None = Field(default=None, max_length=5000)
    scope: str | None = Field(default=None, pattern=r"^(organization|branch|service)$")
    branch_id: str | None = None
    settings: dict[str, Any] | None = None
    is_active: bool | None = None
    fields: list[FormFieldInput] | None = None

    @field_validator("fields")
    @classmethod
    def _unique_keys(cls, v):
        if v is not None:
            keys = [f.key for f in v]
            if len(keys) != len(set(keys)):
                raise ValueError("Field keys must be unique")
        return v


class BookingFormRead(BookingFormBase):
    id: str
    slug: str
    version: int
    is_template: bool
    is_published: bool
    is_active: bool
    fields: list[FormFieldRead] = Field(default_factory=list)
    service_count: int = 0
    response_count: int = 0
    created_at: datetime
    updated_at: datetime


class FormResponseRead(APIModel):
    id: str
    form_id: str
    form_name: str
    form_version: int
    appointment_id: str | None
    customer_id: str | None
    answers: dict[str, Any]
    attachments: list[Any] | None
    created_at: datetime


class PublicForm(APIModel):
    id: str
    name: str
    version: int
    description: str | None
    instructions: str | None
    fields: list[FormFieldRead]
