"""n8n: outgoing events through the platform's signed webhook system, incoming actions through a signed endpoint.

Outgoing: the connector owns one webhook endpoint (HMAC-SHA256 signature ``X-Webhook-Signature: t=<unix>,v1=<hex>`` over
"<t>.<body>", retries with growing waits, delivery log, safe redelivery). Incoming: POST /api/v1/automation/n8n/<id>
signed the same way with a separate secret, a fresh timestamp (5 minutes) and a request id that can be used only once.
n8n is never the booking engine: incoming actions go through the same services and rules as staff actions.
"""
from __future__ import annotations

import re
import secrets as pysecrets

from app.connectors.base import Adapter
from app.core.exceptions import ValidationFailed
from app.integrations.http import IntegrationAPIError

ACTIONS = {
    "send_notification": "Send an approved notification for an appointment (confirmation, reminder, follow-up)",
    "create_follow_up": "Create a follow-up task for the clinic",
    "trigger_reminder": "Send the appointment reminder now",
    "get_appointment": "Read one appointment's details",
    "update_customer": "Update a patient's tags or message preferences",
}


def parse_list(text: str | None, allowed: set[str] | None = None, label: str = "value") -> list[str]:
    items = [p.strip() for p in re.split(r"[,\s]+", text or "") if p.strip()]
    if allowed is not None:
        unknown = [i for i in items if i not in allowed and i != "*"]
        if unknown:
            raise ValidationFailed(f"Unknown {label}: {', '.join(unknown)}.", code="invalid_setting")
    return items


class N8n(Adapter):
    def endpoint(self):
        from sqlalchemy import select

        from app.models import WebhookEndpoint

        pid = self.ctx.state("endpoint_id")
        return self.ctx.db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.public_id == pid, WebhookEndpoint.organization_id == self.ctx.org.id)) if pid else None

    def configure(self, actor, meta) -> dict[str, str]:
        """Create or update the outgoing webhook endpoint. Returns secrets to show once (only when they are new)."""
        from app.schemas.developer import WebhookCreate, WebhookUpdate
        from app.services.developer_service import DeveloperService
        from app.webhooks.catalog import EVENTS

        cfg = self.ctx.config
        events = parse_list(cfg.get("events") or "*", set(EVENTS), "event") or ["*"]
        parse_list(cfg.get("allowed_actions"), set(ACTIONS), "action")
        svc = DeveloperService(self.ctx.db, self.ctx.org, actor, meta)
        shown: dict[str, str] = {}
        ep = self.endpoint()
        if ep is None:
            created = svc.create_endpoint(WebhookCreate(name="n8n automation", url=cfg["url"], events=events))
            self.ctx.set_state(endpoint_id=created.id)
            shown["outgoing_secret"] = created.secret
        else:
            svc.update_endpoint(ep, WebhookUpdate(url=cfg["url"], events=events, is_active=self.ctx.integ.is_enabled))
        creds = self.ctx.secrets()
        if not creds.get("incoming_secret"):
            creds["incoming_secret"] = "whsec_" + pysecrets.token_urlsafe(32)
            self.ctx.save_secrets(creds)
            shown["incoming_secret"] = creds["incoming_secret"]
        return shown

    def rotate(self, actor, meta) -> dict[str, str]:
        from app.services.developer_service import DeveloperService

        out = {}
        ep = self.endpoint()
        if ep is not None:
            out["outgoing_secret"] = DeveloperService(self.ctx.db, self.ctx.org, actor, meta).rotate_secret(ep)
        creds = self.ctx.secrets()
        creds["incoming_secret"] = out["incoming_secret"] = "whsec_" + pysecrets.token_urlsafe(32)
        self.ctx.save_secrets(creds)
        return out

    def test(self) -> str:
        """Send a real signed ping to n8n now and wait for its answer."""
        from app.core.enums import WebhookDeliveryStatus
        from app.services.developer_service import DeveloperService

        ep = self.endpoint()
        if ep is None:
            raise IntegrationAPIError("Save the n8n Webhook URL first.")
        ev = DeveloperService(self.ctx.db, self.ctx.org).ping(ep)  # sent right away, signed like every event
        if ev.status != WebhookDeliveryStatus.DELIVERED:
            raise IntegrationAPIError(f"n8n did not accept the test event: {ev.last_error or 'no answer'}. Is the workflow active and the URL the Production URL?")
        return f"n8n answered the signed test event (HTTP {ev.response_status})"

    def disconnect(self) -> None:
        ep = self.endpoint()
        if ep is not None:
            ep.is_active = False
        self.ctx.save_secrets({})
