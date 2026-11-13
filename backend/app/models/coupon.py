from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class Coupon(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Discount code applied at booking. Redemptions are counted from appointments, not a counter,
    so cancelled or expired bookings automatically give the redemption back."""

    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[str] = mapped_column(String(8), nullable=False)  # percent | flat
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)  # percent (1-100) or paise
    max_discount_paise: Mapped[int | None] = mapped_column(Integer)
    min_amount_paise: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    per_customer_limit: Mapped[int | None] = mapped_column(Integer)
    service_ids: Mapped[list[Any] | None] = mapped_column(nullable=True)  # public ids; empty = all services
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
