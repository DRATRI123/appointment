from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConsultationMode, ServiceKind, ServicePaymentMode
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class ServiceCategory(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "service_categories"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(512))
    icon: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("service_categories.id", ondelete="SET NULL"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    services: Mapped[list["Service"]] = relationship(back_populates="category")


class Service(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default=ServiceKind.STANDARD, nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(512))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultation_mode: Mapped[str] = mapped_column(
        String(16), default=ConsultationMode.IN_PERSON, nullable=False
    )
    # money in paise
    price_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discounted_price_paise: Mapped[int | None] = mapped_column(Integer)
    payment_mode: Mapped[str] = mapped_column(
        String(24), default=ServicePaymentMode.FULL_ADVANCE, nullable=False
    )
    advance_amount_paise: Mapped[int | None] = mapped_column(Integer)
    advance_percent: Mapped[int | None] = mapped_column(Integer)
    tax_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    # booking rules
    min_notice_minutes: Mapped[int | None] = mapped_column(Integer)
    max_advance_days: Mapped[int | None] = mapped_column(Integer)
    cancellation_policy: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    booking_rules: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text)
    booking_form_id: Mapped[int | None] = mapped_column(
        ForeignKey("booking_forms.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_within_days: Mapped[int | None] = mapped_column(Integer)
    upi_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("upi_accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_bookable_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    category: Mapped[ServiceCategory | None] = relationship(back_populates="services")
    pricing: Mapped[list["ServicePricing"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class ServicePricing(PKMixin, TimestampMixin, Base):
    """Branch-specific price override and availability of a service."""

    __tablename__ = "service_pricing"
    __table_args__ = (UniqueConstraint("service_id", "branch_id"),)

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_paise: Mapped[int | None] = mapped_column(Integer)
    discounted_price_paise: Mapped[int | None] = mapped_column(Integer)
    advance_amount_paise: Mapped[int | None] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    service: Mapped[Service] = relationship(back_populates="pricing")


class ServicePackage(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "service_packages"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validity_days: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list["ServicePackageItem"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )


class ServicePackageItem(PKMixin, Base):
    __tablename__ = "service_package_items"
    __table_args__ = (UniqueConstraint("package_id", "service_id"),)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("service_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    package: Mapped[ServicePackage] = relationship(back_populates="items")
