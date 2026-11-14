from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ACTIVE_APPOINTMENT_STATUSES, AppointmentSource, AppointmentStatus, HoldStatus
from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, TenantMixin, TimestampMixin

_ACTIVE_STATUS_SQL = ", ".join(f"'{s}'" for s in ACTIVE_APPOINTMENT_STATUSES)


class Appointment(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # Hard stop against double booking: one active appointment per professional/branch/start.
        # Capacity > 1 services use appointment_slots.booked_count and set slot_sequence > 0.
        Index(
            "uq_appointments_active_slot",
            "professional_id",
            "branch_id",
            "start_at",
            "slot_sequence",
            unique=True,
            sqlite_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
            postgresql_where=text(f"status IN ({_ACTIVE_STATUS_SQL})"),
        ),
        Index("ix_appointments_org_start", "organization_id", "start_at"),
        # First-visit dates per customer (new vs returning on the dashboard): answered from the index alone.
        Index("ix_appointments_org_customer_start", "organization_id", "customer_id", "start_at", postgresql_include=["status"]),
        Index("ix_appointments_org_status", "organization_id", "status"),
        Index("ix_appointments_customer_start", "customer_id", "start_at"),
        Index("ix_appointments_professional_start", "professional_id", "start_at"),
    )

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="RESTRICT"), nullable=False
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    dependent_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_dependents.id", ondelete="SET NULL")
    )
    hold_id: Mapped[int | None] = mapped_column(ForeignKey("booking_holds.id", ondelete="SET NULL"))
    parent_appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL")
    )  # follow-ups, reschedules, recurring series
    recurrence_group_id: Mapped[str | None] = mapped_column(String(36), index=True)
    group_booking_id: Mapped[str | None] = mapped_column(String(36), index=True)

    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    slot_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultation_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=AppointmentStatus.DRAFT, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), default=AppointmentSource.ONLINE, nullable=False)
    booked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_walk_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_follow_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # money (paise) - always computed on the backend
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    subtotal_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_amount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    advance_due_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_amount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(48))
    pricing_snapshot: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    customer_notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    meeting_link: Mapped[str | None] = mapped_column(String(512))
    meeting_provider: Mapped[str | None] = mapped_column(String(32))
    external_calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    payment_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    checked_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    status_history: Mapped[list[AppointmentStatusHistory]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan", order_by="AppointmentStatusHistory.id"
    )


class AppointmentStatusHistory(PKMixin, Base):
    __tablename__ = "appointment_status_history"

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    appointment: Mapped[Appointment] = relationship(back_populates="status_history")


class AppointmentReschedule(PKMixin, TenantMixin, Base):
    __tablename__ = "appointment_reschedules"

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    old_end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    new_start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    new_end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    old_professional_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id", ondelete="SET NULL"))
    new_professional_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id", ondelete="SET NULL"))
    rescheduled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    rescheduled_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class AppointmentCancellation(PKMixin, TenantMixin, Base):
    __tablename__ = "appointment_cancellations"

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_by_role: Mapped[str | None] = mapped_column(String(32))  # customer, staff, system
    reason: Mapped[str | None] = mapped_column(Text)
    policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    refund_eligible_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class BookingHold(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """Temporary slot reservation while the customer completes the booking form and payment."""

    __tablename__ = "booking_holds"
    __table_args__ = (
        Index(
            "uq_booking_holds_active_slot",
            "professional_id",
            "branch_id",
            "start_at",
            "slot_sequence",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_booking_holds_expires", "status", "expires_at"),
    )

    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    professional_id: Mapped[int] = mapped_column(
        ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    session_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    slot_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=HoldStatus.ACTIVE, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Waitlist(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (UniqueConstraint("organization_id", "customer_id", "professional_id", "preferred_date"),)

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    professional_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id", ondelete="CASCADE"))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    preferred_date: Mapped[datetime | None] = mapped_column(UTCDateTime)
    preferred_window: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
