from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin
from app.models.organization import Organization


class Branch(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()
    timezone: Mapped[str | None] = mapped_column(String(64))  # falls back to organization
    # {"mon": [["09:00","13:00"],["16:00","20:00"]], ...}
    business_hours: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="branches")
    settings: Mapped[list["BranchSetting"]] = relationship(
        back_populates="branch", cascade="all, delete-orphan"
    )


class BranchSetting(PKMixin, TimestampMixin, Base):
    __tablename__ = "branch_settings"
    __table_args__ = (UniqueConstraint("branch_id", "namespace", "key"),)

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(48), nullable=False)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    branch: Mapped[Branch] = relationship(back_populates="settings")
