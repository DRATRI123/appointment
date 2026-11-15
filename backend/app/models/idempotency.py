"""Idempotency keys: a retried request with the same key gets the first response instead of doing the work twice."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, TimestampMixin


class IdempotencyKey(PKMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # One key per caller per operation. Two simultaneous requests with the same key: the second insert fails
        # (PostgreSQL waits for the first to commit), and it gets the first one's response.
        UniqueConstraint("organization_id", "scope", "principal", "key", name="uq_idempotency_keys_owner_key"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)  # public_booking | booking | payment_submit
    principal: Mapped[str] = mapped_column(String(100), nullable=False)  # hash of who sent it (session, user, key)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_body: Mapped[str | None] = mapped_column(Text)  # AES-256-GCM: it can hold a booking's access token
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
