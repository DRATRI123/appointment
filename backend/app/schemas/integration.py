from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class IntegrationRead(APIModel):
    id: str
    provider: str
    name: str
    status: str
    is_enabled: bool
    account: str | None
    config: dict[str, Any]
    professional_id: str | None
    professional_name: str | None
    connected_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None


class MeetingPreference(APIModel):
    provider: str = Field(default="auto", pattern=r"^(auto|google_meet|zoom|manual|none)$")
    manual_url: str | None = Field(default=None, max_length=512)
    zoom_user: str | None = Field(default=None, max_length=255)

    @field_validator("manual_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not v.startswith("https://"):
            raise ValueError("Use a full https:// meeting link.")
        return v


class ProfessionalConnections(APIModel):
    professional_id: str
    professional_name: str
    is_me: bool
    google: IntegrationRead | None
    meeting: MeetingPreference
    effective_meeting_provider: str
    feed_url: str | None


class IntegrationsOverview(APIModel):
    google_configured: bool
    google_redirect_uri: str
    zoom: IntegrationRead | None
    professionals: list[ProfessionalConnections]
    can_manage_all: bool


class GoogleConnect(APIModel):
    professional_id: str
    return_to: str = Field(default="/admin/integrations", pattern=r"^/(admin|professional)(/[a-z0-9\-/]*)?$")


class AuthorizationURL(APIModel):
    authorization_url: str


class IntegrationUpdate(APIModel):
    """Google: calendar_id, create_meet, block_busy, show_patient_names. Zoom: default_user. Both: is_enabled."""

    calendar_id: str | None = Field(default=None, max_length=255)
    create_meet: bool | None = None
    block_busy: bool | None = None
    show_patient_names: bool | None = None
    default_user: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None


class ZoomConnect(APIModel):
    account_id: str = Field(min_length=4, max_length=128)
    client_id: str = Field(min_length=4, max_length=128)
    client_secret: str = Field(min_length=4, max_length=256)
    default_user: str | None = Field(default=None, max_length=255)


class IntegrationLogRead(APIModel):
    action: str
    status: str
    error: str | None
    duration_ms: int | None
    created_at: datetime


class SyncIssue(APIModel):
    id: int
    provider: str
    appointment_id: str
    appointment_reference: str
    appointment_start_at: datetime
    professional_name: str | None
    status: str
    attempts: int
    last_error: str | None
    next_attempt_at: datetime | None


class MeetingLinkUpdate(APIModel):
    meeting_link: str | None = Field(default=None, max_length=512)

    @field_validator("meeting_link")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not v.startswith("https://"):
            raise ValueError("Use a full https:// meeting link.")
        return v
