from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Message(APIModel):
    detail: str


class HealthStatus(APIModel):
    status: str
    app: str
    version: str
    environment: str
    database: str | None = None
    checks: dict[str, Any] | None = None
