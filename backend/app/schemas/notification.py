from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class EventInfo(APIModel):
    code: str
    label: str
    audience: str
    description: str
    variables: list[str]
    default_channels: list[str]
    enabled: bool
    channels: list[str]


class TemplateRead(APIModel):
    event: str
    channel: str
    subject: str | None
    body: str
    provider_template_id: str | None
    is_custom: bool
    is_active: bool
    default_subject: str | None
    default_body: str
    updated_at: datetime | None = None


class TemplateUpsert(APIModel):
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=5000)
    provider_template_id: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class PreviewRequest(APIModel):
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class PreviewResponse(APIModel):
    subject: str | None
    body: str
    html: str | None
    sms_segments: int | None = None
    unknown_variables: list[str]


class TestSendRequest(APIModel):
    channel: str = Field(pattern=r"^(email|sms|whatsapp)$")
    to: str = Field(min_length=5, max_length=255)


class ProviderStatus(APIModel):
    channel: str
    provider: str | None
    configured: bool
    is_console: bool
    error: str | None
    enabled_for_organization: bool


class NotificationRead(APIModel):
    id: str
    event: str
    channel: str
    status: str
    recipient: str | None
    recipient_name: str | None
    subject: str | None
    body: str
    scheduled_for: datetime | None
    sent_at: datetime | None
    read_at: datetime | None
    attempts: int
    last_error: str | None
    appointment_reference: str | None
    created_at: datetime


class NotificationLogRead(APIModel):
    provider: str
    provider_message_id: str | None
    status: str
    error: str | None
    created_at: datetime


class NotificationDetail(NotificationRead):
    logs: list[NotificationLogRead]
    payload: dict[str, Any] | None


class NotificationStats(APIModel):
    sent_today: int
    failed: int
    scheduled: int
    pending: int


class InboxItem(APIModel):
    id: str
    event: str
    title: str | None
    body: str
    link: str | None
    organization_id: str | None
    read_at: datetime | None
    created_at: datetime


class Inbox(APIModel):
    items: list[InboxItem]
    unread: int


class Preferences(APIModel):
    email: bool = True
    sms: bool = True
    whatsapp: bool = False
    reminders: bool = True


class PreferencesUpdate(APIModel):
    email: bool | None = None
    sms: bool | None = None
    whatsapp: bool | None = None
    reminders: bool | None = None


class EventSetting(APIModel):
    enabled: bool = True
    channels: list[str] = Field(default_factory=list)


class NotificationSettings(APIModel):
    email_enabled: bool = True
    sms_enabled: bool = False
    whatsapp_enabled: bool = False
    in_app_enabled: bool = True
    notify_staff_on_booking: bool = True
    reminder_hours: list[float] = Field(default_factory=lambda: [24, 2], max_length=3)
    reply_to_email: str = Field(default="", max_length=255)
    events: dict[str, EventSetting] = Field(default_factory=dict)

    @field_validator("reminder_hours")
    @classmethod
    def _hours(cls, v: list[float]) -> list[float]:
        for h in v:
            if not 0.25 <= h <= 336:
                raise ValueError("Reminder hours must be between 0.25 (15 minutes) and 336 (14 days).")
        return sorted(set(v), reverse=True)

    @field_validator("reply_to_email")
    @classmethod
    def _reply(cls, v: str) -> str:
        v = v.strip()
        if v and ("@" not in v or " " in v):
            raise ValueError("Enter a valid email address or leave it empty.")
        return v

    @field_validator("events")
    @classmethod
    def _events(cls, v: dict[str, EventSetting]) -> dict[str, EventSetting]:
        from app.notifications.catalog import CHANNELS, EVENTS

        for code, cfg in v.items():
            if code not in EVENTS:
                raise ValueError(f"Unknown event: {code}")
            bad = [c for c in cfg.channels if c not in CHANNELS or c not in EVENTS[code].templates]
            if bad:
                raise ValueError(f"Unsupported channels for {code}: {', '.join(bad)}")
            if EVENTS[code].audience == "staff" and any(c in ("sms", "whatsapp") for c in cfg.channels):
                raise ValueError("Staff alerts go by in-app message or email.")
        return v
