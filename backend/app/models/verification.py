"""Multi-channel verification: one-time-code challenges and each clinic's own delivery accounts."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class OtpChallenge(PKMixin, PublicIdMixin, TimestampMixin, Base):
    """One code sent to one destination for one purpose. Only an HMAC of the code is stored."""

    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_challenges_org_destination_created", "organization_id", "destination", "created_at"),
        Index("ix_otp_challenges_org_ip_created", "organization_id", "ip_address", "created_at"),
        Index("ix_otp_challenges_org_session_created", "organization_id", "session_key", "created_at"),
    )

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # booking
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # sms | email | whatsapp
    destination: Mapped[str] = mapped_column(String(255), nullable=False)  # E.164 mobile or lower-case email
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    resend_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    invalidated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    session_key: Mapped[str | None] = mapped_column(String(64))
    hold_public_id: Mapped[str | None] = mapped_column(String(36))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_message_id: Mapped[str | None] = mapped_column(String(160))
    delivery_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|sent|failed
    delivery_error: Mapped[str | None] = mapped_column(String(300))


class MessagingProviderConfig(PKMixin, TimestampMixin, Base):
    """A clinic's own SMS / email / WhatsApp account. Secrets are stored encrypted and never returned by the API."""

    __tablename__ = "messaging_provider_configs"
    __table_args__ = (UniqueConstraint("organization_id", "channel"),)

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # msg91 | twilio | smtp | meta
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(nullable=False)  # non-secret: sender id, template ids, host, ...
    secrets_encrypted: Mapped[str | None] = mapped_column(Text)  # AES-GCM (DATA_ENCRYPTION_KEY) JSON of secret fields
    secret_hints: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)  # {"auth_key": "…3f9a"}
    last_test_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_error: Mapped[str | None] = mapped_column(String(300))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
