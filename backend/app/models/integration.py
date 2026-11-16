from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import IntegrationStatus, WebhookDeliveryStatus
from app.core.types import UTCDateTime
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
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)

    logs: Mapped[list[IntegrationLog]] = relationship(
        back_populates="integration", cascade="all, delete-orphan"
    )


class APIKey(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """Developer API key. Only the hash is stored; prefix shown in the UI for identification."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False, index=True)  # "ak_live_" + 8 hex = 16
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[list[Any] | None] = mapped_column(nullable=True)  # permission codes
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
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
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    deliveries: Mapped[list[WebhookEvent]] = relationship(
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
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    integration: Mapped[Integration] = relationship(back_populates="logs")


class AppointmentExternalEvent(PKMixin, TenantMixin, TimestampMixin, Base):
    """Mirror of one appointment in one external system (a Google Calendar event or a Zoom meeting).

    The worker reconciles each row towards the appointment's current state: create, update or delete.
    """

    __tablename__ = "appointment_external_events"
    __table_args__ = (
        UniqueConstraint("appointment_id", "integration_id"),
        Index("ix_appt_external_status_next", "status", "next_attempt_at"),
    )

    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # google_calendar | zoom
    external_id: Mapped[str | None] = mapped_column(String(255))
    external_url: Mapped[str | None] = mapped_column(String(1024))  # event htmlLink / meeting join url
    meeting_url: Mapped[str | None] = mapped_column(String(1024))
    synced_start_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|synced|deleted|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class ExternalBusyBlock(PKMixin, TenantMixin, Base):
    """Busy time imported from a professional's external calendar; blocks booking slots like leave."""

    __tablename__ = "external_busy_blocks"
    __table_args__ = (Index("ix_external_busy_pro_time", "professional_id", "start_at", "end_at"),)

    professional_id: Mapped[int] = mapped_column(ForeignKey("professionals.id", ondelete="CASCADE"), nullable=False)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    title: Mapped[str | None] = mapped_column(String(64))  # "Busy" only; event titles are not stored
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class ApiKeyUsage(PKMixin, TenantMixin, Base):
    """Requests per API key per day (UTC), for the developer portal and platform usage pages."""

    __tablename__ = "api_key_usage"
    __table_args__ = (UniqueConstraint("api_key_id", "day"),)

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    client_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    server_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class IntegrationSyncItem(PKMixin, TenantMixin, TimestampMixin, Base):
    """One record (patient, document, payment, refund, appointment) mirrored in one external system (CRM, accounting,
    Google Contacts/Drive). The worker pushes the record's current state; ``external_id`` prevents duplicates."""

    __tablename__ = "integration_sync_items"
    __table_args__ = (
        UniqueConstraint("integration_id", "entity_type", "entity_id"),
        Index("ix_integration_sync_status_next", "status", "next_attempt_at"),
    )

    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)  # customer | document | payment | refund | appointment
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(8), default="upsert", nullable=False)  # upsert | delete
    external_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | synced | failed | dead | skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str | None] = mapped_column(String(64))  # unchanged data is not sent again


class AutomationRequest(PKMixin, TenantMixin, Base):
    """Incoming automation calls (n8n): one row per request id, so a replayed request is refused."""

    __tablename__ = "automation_requests"
    __table_args__ = (UniqueConstraint("integration_id", "request_id"),)

    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | refused | failed
    detail: Mapped[str | None] = mapped_column(String(300))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)


class FollowUpTask(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """A to-do for the clinic (call back, send a report), created by staff or an approved automation."""

    __tablename__ = "follow_up_tasks"

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(String(1000))
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | done | cancelled
    source: Mapped[str] = mapped_column(String(32), default="staff", nullable=False)  # staff | n8n
    integration_id: Mapped[int | None] = mapped_column(ForeignKey("integrations.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ApiAccessLog(PKMixin, TenantMixin, Base):
    """One row per API-key request (method, route, status, time): who used the API and how. Kept 30 days."""

    __tablename__ = "api_access_logs"
    __table_args__ = (Index("ix_api_access_key_time", "api_key_id", "created_at"),)

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)  # route template, never query strings
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
