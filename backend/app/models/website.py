"""Clinic website: one draft/published document per organization, plus every published version for restore."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, TimestampMixin


class Website(PKMixin, TimestampMixin, Base):
    __tablename__ = "websites"

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    draft: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    published: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    # Optimistic locking: every draft save bumps it; a save based on an older value is refused (two admins editing).
    lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    draft_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    draft_updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class WebsiteVersion(PKMixin, TimestampMixin, Base):
    __tablename__ = "website_versions"
    __table_args__ = (UniqueConstraint("organization_id", "version"),)

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(200))
