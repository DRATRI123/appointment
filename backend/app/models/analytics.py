"""Cookie-free website traffic counters: one row per clinic, day, metric, key and source. No visitor identifiers,
IP addresses or personal data are stored."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PKMixin


class WebsiteDailyStat(PKMixin, Base):
    __tablename__ = "website_daily_stats"
    __table_args__ = (UniqueConstraint("organization_id", "day", "metric", "key", "source"),)

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(24), nullable=False)  # page_view | book_click | booking_view
    key: Mapped[str] = mapped_column(String(80), nullable=False, default="")  # home, page slug, branch slug, "book"
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="direct")  # utm_source, else direct / embed
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
