from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import FormScope
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class BookingForm(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A versioned form definition. Publishing creates a new immutable version row."""

    __tablename__ = "booking_forms"
    __table_args__ = (UniqueConstraint("organization_id", "slug", "version"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default=FormScope.ORGANIZATION, nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    fields: Mapped[list["BookingFormField"]] = relationship(
        back_populates="form", cascade="all, delete-orphan", order_by="BookingFormField.sort_order"
    )


class BookingFormField(PKMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "booking_form_fields"
    __table_args__ = (UniqueConstraint("form_id", "key"),)

    form_id: Mapped[int] = mapped_column(
        ForeignKey("booking_forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(24), nullable=False)
    placeholder: Mapped[str | None] = mapped_column(String(160))
    help_text: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    options: Mapped[list[Any] | None] = mapped_column(nullable=True)  # [{"value","label"}]
    validation: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)  # min, max, regex...
    conditions: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)  # visibility rules
    default_value: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    form: Mapped[BookingForm] = relationship(back_populates="fields")


class BookingFormResponse(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "booking_form_responses"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("booking_forms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    answers: Mapped[dict[str, Any]] = mapped_column(nullable=False)  # {field_key: value}
    attachments: Mapped[list[Any] | None] = mapped_column(nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
