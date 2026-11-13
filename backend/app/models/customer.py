from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class Customer(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A customer/patient record scoped to one organization.

    The same person (user) booking with two organizations has two customer rows, so tenant data
    never crosses organizations.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        UniqueConstraint("organization_id", "customer_code"),
        Index("ix_customers_org_mobile", "organization_id", "mobile"),
        Index("ix_customers_org_email", "organization_id", "email"),
    )

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    customer_code: Mapped[str | None] = mapped_column(String(32))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    address: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(512))
    blood_group: Mapped[str | None] = mapped_column(String(8))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    communication_preferences: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    consent: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    tags: Mapped[list[Any] | None] = mapped_column(nullable=True)
    saved_professional_ids: Mapped[list[Any] | None] = mapped_column(nullable=True)
    saved_branch_ids: Mapped[list[Any] | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(String(32))
    registered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_visit_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    dependents: Mapped[list["CustomerDependent"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerDependent(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer_dependents"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    relationship_label: Mapped[str | None] = mapped_column(String(48))  # spouse, child, parent
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    mobile: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="dependents")


class CustomerNote(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """Clinical or administrative note. Body is encrypted at the application layer (Phase 5)."""

    __tablename__ = "customer_notes"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note_type: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    body_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CustomerDocument(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customer_documents"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(96), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_until: Mapped[date | None] = mapped_column(Date)
