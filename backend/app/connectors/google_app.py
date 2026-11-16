"""The clinic's own Google Cloud app (OAuth client).

Two levels, on purpose:
* Platform (Super admin → Integrations → Google sign-in): only for "Sign in with Google".
* Clinic (Admin → Integrations → Google Cloud app): every Google connection of that clinic (each doctor's Calendar and
  Meet, Gmail, Contacts, Drive) uses the clinic's own client ID and secret. Tokens remember which client issued them;
  if the clinic changes its app, its Google connections must be connected again.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.connectors.base import Adapter
from app.core.enums import IntegrationStatus
from app.core.exceptions import ValidationFailed
from app.integrations.http import IntegrationAPIError

KEY = "google_app"


@dataclass(frozen=True)
class GoogleClient:
    client_id: str
    client_secret: str


def clinic_client(db, organization_id: int) -> GoogleClient | None:
    """The clinic's Google app, only when it is switched on and passed its test."""
    import json

    from app.models import Integration
    from app.security.crypto import decrypt_text

    row = db.scalar(select(Integration).where(Integration.organization_id == organization_id, Integration.provider == KEY,
                                              Integration.professional_id.is_(None), Integration.is_enabled.is_(True),
                                              Integration.status == IntegrationStatus.CONNECTED))
    if row is None or not row.credentials_encrypted:
        return None
    client_id = (row.config or {}).get("client_id")
    secret = json.loads(decrypt_text(row.credentials_encrypted)).get("client_secret")
    return GoogleClient(client_id, secret) if client_id and secret else None


def require_client(db, organization_id: int) -> GoogleClient:
    client = clinic_client(db, organization_id)
    if client is None:
        raise ValidationFailed("Add your clinic's Google Cloud app first (Integrations → Google Cloud app: client ID, secret, then Test).",
                               code="google_app_missing")
    return client


class GoogleApp(Adapter):
    def test(self) -> str:
        from app.integrations.google_calendar import redirect_uri
        from app.services.platform_tests import test_google

        ok, message = test_google(self.ctx.config.get("client_id"), self.ctx.secrets().get("client_secret"), redirect_uri())
        if not ok:
            raise IntegrationAPIError(message)
        return message
