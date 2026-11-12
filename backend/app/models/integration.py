from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import IntegrationStatus, WebhookDeliveryStatus
from app.models.base import Base, PKMixin, PublicIdMixin, TenantMixin, TimestampMixin


class Integration(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """A configured third-party connection. Secrets are encrypted in ``credentials_encrypted``."""

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "branch_id", "professional_id"),)

    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    professional_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=IntegrationStatus.DISCONNECTED, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)  # non-secret settings
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)  # OAuth tokens / api keys
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    connected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    logs: Mapped[list["IntegrationLog"]] = relationship(
        back_populates="integration", cascade="all, delete-orphan"
    )


class APIKey(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """Developer API key. Only the hash is stored; prefix shown in the UI for identification."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[list[Any] | None] = mapped_column(nullable=True)  # permission codes
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit: Mapped[str | None] = mapped_column(String(32))
    allowed_ips: Mapped[list[Any] | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebhookEndpoint(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoints"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # HMAC signing secret
    events: Mapped[list[Any]] = mapped_column(nullable=False)  # subscribed event names
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_version: Mapped[str] = mapped_column(String(8), default="v1", nullable=False)
    headers: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    deliveries: Mapped[list["WebhookEvent"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookEvent(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """One delivery attempt record per endpoint per event (with retries tracked in-row)."""

    __tablename__ = "webhook_events"
    __table_args__ = (Index("ix_webhook_events_status_next", "status", "next_attempt_at"),)

    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # idempotency key
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=WebhookDeliveryStatus.PENDING, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")


class IntegrationLog(PKMixin, Base):
    __tablename__ = "integration_logs"

    integration_id: Mapped[int] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # outbound / inbound
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    integration: Mapped[Integration] = relationship(back_populates="logs")
