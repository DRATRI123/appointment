from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field

from app.schemas.common import APIModel


class AuditLogRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    actor_type: str
    actor_label: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    request_id: str | None
    purpose: str | None
    created_at: datetime
