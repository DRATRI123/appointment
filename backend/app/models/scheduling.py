from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import LeaveType
from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, TenantMixin, TimestampMixin


class Schedule(PKMixin, TenantMixin, TimestampMixin, Base):
    """Weekly recurring working window for a professional at a branch.

    One row per (professional, branch, weekday, window). Multiple windows per day allow lunch breaks.
    """

    __tablename__ = "schedules"
    __table_args__ = (
        Index("ix_schedules_prof_branch_day", "professional_id", "branch_id", "weekday"),
    )

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_time: Mapped[time] = mapped_column(Time, nullable=False)  # local to branch timezone
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int | None] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    consultation_mode: Mapped[str | None] = mapped_column(String(16))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ScheduleException(PKMixin, TenantMixin, TimestampMixin, Base):
    """Date-specific override: extra window, modified hours or a full-day block."""

    __tablename__ = "schedule_exceptions"
    __table_args__ = (Index("ix_schedule_exceptions_prof_date", "professional_id", "date"),)

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255))


class Holiday(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("organization_id", "branch_id", "date"),)

    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_recurring_yearly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProfessionalLeave(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "professional_leaves"
    __table_args__ = (Index("ix_leaves_prof_range", "professional_id", "start_at", "end_at"),)

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    leave_type: Mapped[str] = mapped_column(String(16), default=LeaveType.LEAVE, nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="approved", nullable=False)


class AppointmentSlot(PKMixin, TenantMixin, TimestampMixin, Base):
    """Optional materialised slot (used for capacity > 1 and for calendar performance).

    The source of truth for availability is the schedule computation + appointments + holds; this
    table caches generated slots and tracks booked counts for capacity-based services.
    """

    __tablename__ = "appointment_slots"
    __table_args__ = (
        UniqueConstraint("professional_id", "branch_id", "start_at"),
        Index("ix_slots_prof_branch_start", "professional_id", "branch_id", "start_at"),
    )

    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    held_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)
