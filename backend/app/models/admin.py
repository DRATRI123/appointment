from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DDL, ForeignKey, Index, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import UTCDateTime
from app.models.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class AuditLog(PKMixin, PublicIdMixin, Base):
    """Append-only record of privileged and sensitive actions."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user, api_key, system
    actor_label: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(48))
    before: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64))
    purpose: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # HMAC-SHA256 (audit purpose key) over the row's content: an edited row no longer matches (app.ops.verify_audit).
    signature: Mapped[str | None] = mapped_column(String(64))


class SystemSetting(PKMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)


# Audit history is append-only on PostgreSQL: the database itself refuses UPDATE and DELETE on audit_logs, whoever asks
# (migration 73128aa5cd2f creates it for existing databases; this creates it wherever the table is created).
_AUDIT_APPEND_ONLY = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: history cannot be changed or deleted' USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();
"""
event.listen(AuditLog.__table__, "after_create", DDL(_AUDIT_APPEND_ONLY).execute_if(dialect="postgresql"))
