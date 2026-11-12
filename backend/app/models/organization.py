from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrganizationStatus, SubscriptionStatus
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.branch import Branch


class Organization(PKMixin, PublicIdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)  # used in references
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    business_type: Mapped[str | None] = mapped_column(String(64))  # clinic, hospital, salon ...
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=OrganizationStatus.ACTIVE, nullable=False, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    settings: Mapped[list["OrganizationSetting"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    domains: Mapped[list["OrganizationDomain"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    branches: Mapped[list["Branch"]] = relationship(back_populates="organization")


class OrganizationSetting(PKMixin, TimestampMixin, Base):
    """Namespaced key/value JSON settings: booking, cancellation, payment, notification, branding."""

    __tablename__ = "organization_settings"
    __table_args__ = (UniqueConstraint("organization_id", "namespace", "key"),)

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(48), nullable=False)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="settings")


class OrganizationDomain(PKMixin, TimestampMixin, Base):
    __tablename__ = "organization_domains"

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[str | None] = mapped_column(String(128))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="domains")


class OrganizationSubscription(PKMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "organization_subscriptions"

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_code: Mapped[str] = mapped_column(String(48), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=SubscriptionStatus.TRIAL, nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    limits: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
