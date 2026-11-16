"""Shared plumbing for connector adapters: settings, encrypted credentials, logs and OAuth tokens."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import IntegrationStatus
from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError, check, request
from app.models import Integration, IntegrationLog, Organization
from app.security.crypto import decrypt_text, encrypt_text


@dataclass
class Ctx:
    db: Session
    org: Organization
    integ: Integration

    @property
    def config(self) -> dict[str, Any]:
        from app.connectors.registry import get

        conn = get(self.integ.provider)
        return {**(conn.defaults if conn else {}), **{k: v for k, v in (self.integ.config or {}).items() if not k.startswith("_")}}

    def secrets(self) -> dict[str, Any]:
        return json.loads(decrypt_text(self.integ.credentials_encrypted)) if self.integ.credentials_encrypted else {}

    def save_secrets(self, data: dict[str, Any]) -> None:
        self.integ.credentials_encrypted = encrypt_text(json.dumps(data)) if data else None

    def set_state(self, **values: Any) -> None:
        """Internal values (folder ids, last test) kept next to the settings, under keys starting with "_"."""
        cfg = dict(self.integ.config or {})
        cfg.update({f"_{k}": v for k, v in values.items()})
        self.integ.config = cfg

    def state(self, key: str, default: Any = None) -> Any:
        return (self.integ.config or {}).get(f"_{key}", default)

    def log(self, action: str, status: str, *, error: str | None = None, started: float | None = None, detail: dict | None = None) -> None:
        self.db.add(IntegrationLog(integration_id=self.integ.id, direction="outbound", action=action, status=status, request=detail,
                                   error=(error or None) and error[:1000],
                                   duration_ms=int((time.monotonic() - started) * 1000) if started else None, created_at=utcnow()))

    def reconnect_needed(self, message: str) -> None:
        self.integ.status, self.integ.last_error = IntegrationStatus.ERROR, message


class Adapter:
    """Base class. ``test`` returns a short description of the connected account or raises IntegrationAPIError."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx

    def test(self) -> str:  # pragma: no cover - every adapter overrides it
        raise NotImplementedError

    def push(self, entity_type: str, obj: Any, external_id: str | None) -> str | None:
        raise IntegrationAPIError(f"{self.ctx.integ.provider} does not sync {entity_type}.")

    def remove(self, entity_type: str, external_id: str) -> None:
        return None


# ------------------------------------------------------------------------------------------------ Google tokens
def google_access_token(ctx: Ctx) -> str:
    from app.services.integration_service import google_token

    try:
        return google_token(ctx.db, ctx.integ)
    except IntegrationAPIError as exc:
        if exc.reconnect:
            ctx.reconnect_needed("Google access was revoked or has expired. Connect again.")
        raise


# ------------------------------------------------------------------------------------------------ Zoho OAuth
def zoho_accounts(dc: str) -> str:
    return f"https://accounts.zoho.{dc}"


def zoho_api_domain(ctx: Ctx) -> str:
    return ctx.secrets().get("api_domain") or f"https://www.zohoapis.{ctx.config.get('data_center') or 'in'}"


def zoho_token_request(dc: str, data: dict[str, str]) -> dict[str, Any]:
    body = check(request("POST", f"{zoho_accounts(dc)}/oauth/v2/token", data=data), "Zoho token")
    if body.get("error"):  # Zoho answers some errors with HTTP 200
        raise IntegrationAPIError(f"Zoho token failed: {body.get('error')}", reconnect=body.get("error") in ("invalid_code", "invalid_client"), body=body)
    body["expires_at"] = (utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)) - 60)).isoformat()
    return body


def zoho_access_token(ctx: Ctx) -> str:
    creds = ctx.secrets()
    expires = datetime.fromisoformat(creds["expires_at"]) if creds.get("expires_at") else None
    if creds.get("access_token") and expires and expires > utcnow():
        return creds["access_token"]
    if not creds.get("refresh_token"):
        ctx.reconnect_needed("Not connected to Zoho yet. Press Connect.")
        raise IntegrationAPIError("Not connected to Zoho.", reconnect=True)
    try:
        fresh = zoho_token_request(ctx.config.get("data_center") or "in", {"refresh_token": creds["refresh_token"], "grant_type": "refresh_token",
                                                                             "client_id": ctx.config.get("client_id") or "", "client_secret": creds.get("client_secret", "")})
    except IntegrationAPIError as exc:
        if exc.reconnect or exc.status in (400, 401):
            ctx.reconnect_needed("Zoho access was revoked or has expired. Connect again.")
            exc.reconnect, exc.retryable = True, False
        raise
    creds.update(access_token=fresh["access_token"], expires_at=fresh["expires_at"])
    if fresh.get("api_domain"):
        creds["api_domain"] = fresh["api_domain"]
    ctx.save_secrets(creds)
    return fresh["access_token"]


def split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if len(parts) <= 1:
        return "", (parts[0] if parts else "Patient")
    return " ".join(parts[:-1]), parts[-1]
