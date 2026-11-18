"""Patient help desk: a patient's question to their clinic (a ticket) and the conversation on it.

Message text is encrypted at rest (it can carry health details). Staff of one branch see the tickets of their branch
and those not tied to a branch (app/core/branch_scope.py); patients see only their own tickets and never internal notes.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_type import EncryptedText
from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, TenantMixin, TimestampMixin


class SupportTicket(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_support_tickets_org_number"),
        Index("ix_support_tickets_org_status_activity", "organization_id", "status", "last_activity_at"),
        Index("ix_support_tickets_org_customer", "organization_id", "customer_id"),
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)  # #1, #2 … per clinic
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    requester_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")  # open | pending_customer | resolved | closed
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")  # low | normal | high | urgent
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="web")
    first_response_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_customer_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_staff_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_activity_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    unread_by_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unread_by_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5, given by the patient after it is solved


class SupportMessage(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "support_messages"
    __table_args__ = (Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),)

    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # customer | staff | system
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # staff-only note
    body: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    attachment_key: Mapped[str | None] = mapped_column(String(500))  # private storage key (encrypted file)
    attachment_name: Mapped[str | None] = mapped_column(String(160))
    attachment_mime: Mapped[str | None] = mapped_column(String(80))
    attachment_size: Mapped[int | None] = mapped_column(Integer)
