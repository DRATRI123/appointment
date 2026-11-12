from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class Professional(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "professionals"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(32))  # Dr., Mr., Ms.
    profile_photo_url: Mapped[str | None] = mapped_column(String(512))
    qualification: Mapped[str | None] = mapped_column(String(255))
    specialization: Mapped[str | None] = mapped_column(String(160), index=True)
    experience_years: Mapped[int | None] = mapped_column(Integer)
    registration_number: Mapped[str | None] = mapped_column(String(96))
    registration_council: Mapped[str | None] = mapped_column(String(160))
    biography: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[Any] | None] = mapped_column(nullable=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    consultation_modes: Mapped[list[Any] | None] = mapped_column(nullable=True)
    default_fee_paise: Mapped[int | None] = mapped_column(Integer)
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    slot_capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_bookable_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    branches: Mapped[list["ProfessionalBranch"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )
    services: Mapped[list["ProfessionalService"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )


class ProfessionalBranch(PKMixin, TimestampMixin, Base):
    """A professional working at a branch, with branch-specific fee and defaults."""

    __tablename__ = "professional_branches"
    __table_args__ = (UniqueConstraint("professional_id", "branch_id"),)

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_paise: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    buffer_minutes: Mapped[int | None] = mapped_column(Integer)
    room_label: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    professional: Mapped[Professional] = relationship(back_populates="branches")


class ProfessionalService(PKMixin, TimestampMixin, Base):
    __tablename__ = "professional_services"
    __table_args__ = (UniqueConstraint("professional_id", "service_id", "branch_id"),)

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    fee_override_paise: Mapped[int | None] = mapped_column(Integer)
    duration_override_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    professional: Mapped[Professional] = relationship(back_populates="services")
