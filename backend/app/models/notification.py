from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NotificationStatus
from app.models.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class NotificationTemplate(PKMixin, PublicIdMixin, TimestampMixin, Base):
    """Per-channel template with ``{{variable}}`` placeholders. organization_id NULL = platform default."""

    __tablename__ = "notification_templates"
    __table_args__ = (UniqueConstraint("organization_id", "event", "channel", "locale"),)

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN", nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider_template_id: Mapped[str | None] = mapped_column(String(128))  # e.g. WhatsApp template
    variables: Mapped[list[Any] | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Notification(PKMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_org_status_scheduled", "organization_id", "status", "scheduled_for"),
        Index("ix_notifications_recipient_user", "recipient_user_id", "read_at"),
    )

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="SET NULL")
    )
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipient_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    recipient_address: Mapped[str | None] = mapped_column(String(255))  # email / mobile
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=NotificationStatus.PENDING, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), unique=True)

    logs: Mapped[list["NotificationLog"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationLog(PKMixin, Base):
    __tablename__ = "notification_logs"

    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    notification: Mapped[Notification] = relationship(back_populates="logs")
