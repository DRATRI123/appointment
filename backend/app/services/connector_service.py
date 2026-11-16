"""Admin → Integrations (the hub): every integration of a clinic in one place, with real status, settings, tests,
OAuth connections, logs, sync queue and credential rotation.

Statuses: Connected only after a real successful test (or a completed OAuth connection whose account was read back);
"Needs attention" when the last test or sync found a problem; "Not tested yet" after settings changed; "Switched
off"; "Not set up". Built-in features (calendar, Zoom, OTP accounts, webhooks, API keys, Shopify, website) appear as
cards that open their existing pages, so nothing is duplicated.
"""
from __future__ import annotations

import hashlib
import secrets as pysecrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import jwt
from sqlalchemy import func, select

from app.connectors import registry
from app.connectors.base import Ctx, zoho_accounts, zoho_token_request
from app.connectors.sync import adapter_for, enqueue_all
from app.core.enums import IntegrationStatus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError, request
from app.models import Integration, IntegrationLog, IntegrationSyncItem, Organization, User
from app.services.audit_service import RequestMeta, record_audit
from app.services.platform_config import F, _coerce, runtime_settings

CATEGORIES = [
    ("google", "Google services"), ("video", "Calendar & video"), ("email", "Email"), ("whatsapp", "WhatsApp Business"), ("sms", "SMS"),
    ("automation", "n8n automation"), ("shopify", "Shopify"), ("website", "Website"), ("crm", "CRM"), ("accounting", "Accounting"),
    ("storage", "Cloud storage"), ("analytics", "Analytics & monitoring"), ("api", "External API"), ("webhooks", "Webhooks"),
]


def _hint(v: str) -> str:
    return f"…{v[-4:]}" if len(v) > 8 else "set"


def gcal_redirect_uri() -> str:
    from app.integrations.google_calendar import redirect_uri

    return redirect_uri()


def zoho_redirect_uri() -> str:
    return f"{runtime_settings().frontend_url.rstrip('/')}/api/v1/integrations/hub/zoho/callback"


class ConnectorService:
    def __init__(self, db, org: Organization, actor: User | None, meta: RequestMeta | None = None, *, has=lambda p: False):
        self.db, self.org, self.actor, self.meta, self.has = db, org, actor, meta or RequestMeta(), has

    # ------------------------------------------------------------------ helpers
    def connector(self, key: str) -> registry.Connector:
        conn = registry.get(key)
        if conn is None:
            raise NotFoundError("Unknown integration.")
        return conn

    def require(self, conn: registry.Connector) -> None:
        if not (self.has("integrations:write") and self.has(conn.permission)):
            raise PermissionDenied(f"Missing permission: {conn.permission}", code="permission_denied")

    def row(self, key: str) -> Integration | None:
        return self.db.scalar(select(Integration).where(Integration.organization_id == self.org.id, Integration.provider == key,
                                                        Integration.professional_id.is_(None), Integration.branch_id.is_(None)))

    def _ensure_row(self, conn: registry.Connector) -> Integration:
        row = self.row(conn.key)
        if row is None:
            row = Integration(organization_id=self.org.id, provider=conn.key, name=conn.name, status=IntegrationStatus.DISCONNECTED, is_enabled=True,
                              config=dict(conn.defaults))
            self.db.add(row)
            self.db.flush()
        return row

    def _audit(self, action: str, row: Integration | None, **kw) -> None:
        record_audit(self.db, action=action, actor=self.actor, organization_id=self.org.id, entity_type="integration",
                     entity_id=row.public_id if row else None, meta=self.meta, **kw)

    def _values(self, conn: registry.Connector, row: Integration | None) -> dict[str, Any]:
        return {**conn.defaults, **{k: v for k, v in ((row.config if row else None) or {}).items() if not k.startswith("_")}}

    def status(self, conn: registry.Connector, row: Integration | None) -> str:
        if row is None:
            return "not_configured"
        values = self._values(conn, row)
        hints = (row.config or {}).get("_hints") or {}
        missing = [f for f in conn.fields if f.required and not (hints.get(f.name) if f.secret else values.get(f.name))]
        if missing:
            return "not_configured"
        if not row.is_enabled:
            return "disabled"
        test = (row.config or {}).get("_last_test") or {}
        if conn.key == "ga4":
            return "active" if test.get("ok") else ("error" if test else "untested")
        if row.status == IntegrationStatus.ERROR:
            return "error"
        if row.status == IntegrationStatus.CONNECTED and test.get("ok"):
            return "connected"
        if conn.auth in ("google", "zoho") and row.status != IntegrationStatus.CONNECTED:
            return "not_connected"
        return "error" if test and not test.get("ok") else "untested"

    def _fields(self, conn: registry.Connector, row: Integration | None) -> list[dict[str, Any]]:
        values = self._values(conn, row)
        hints = ((row.config if row else None) or {}).get("_hints") or {}
        out = []
        for f in conn.fields:
            item = {"name": f.name, "label": f.label, "kind": f.kind, "choices": list(f.choices), "help": f.help, "when": list(f.when) if f.when else None,
                    "required": f.required, "is_set": bool(hints.get(f.name)) if f.secret else values.get(f.name) not in (None, "")}
            if f.secret:
                item["hint"] = hints.get(f.name)
            else:
                item["value"] = values.get(f.name)
            out.append(item)
        return out

    def _sync_counts(self, row: Integration | None) -> dict[str, int]:
        if row is None:
            return {}
        return dict(self.db.execute(select(IntegrationSyncItem.status, func.count()).where(IntegrationSyncItem.integration_id == row.id)
                                    .group_by(IntegrationSyncItem.status)).all())

    def card(self, conn: registry.Connector, row: Integration | None) -> dict[str, Any]:
        test = ((row.config if row else None) or {}).get("_last_test")
        return {"key": conn.key, "name": conn.name, "category": conn.category, "description": conn.description, "auth": conn.auth,
                "status": self.status(conn, row), "enabled": bool(row and row.is_enabled), "account": row.external_account_id if row else None,
                "last_synced_at": row.last_synced_at if row else None, "last_error": row.last_error if row else None, "last_test": test,
                "syncs": list(conn.syncs), "sync": self._sync_counts(row), "docs": conn.docs, "privacy": conn.privacy, "builtin": False,
                "can_manage": self.has("integrations:write") and self.has(conn.permission)}

    # ------------------------------------------------------------------ overview
    def overview(self) -> dict[str, Any]:
        cards = [self.card(c, self.row(c.key)) for c in registry.CONNECTORS.values()] + self._builtin_cards()
        recent_errors = self.db.execute(
            select(IntegrationLog.action, IntegrationLog.error, IntegrationLog.created_at, Integration.provider)
            .join(Integration, Integration.id == IntegrationLog.integration_id)
            .where(Integration.organization_id == self.org.id, IntegrationLog.status == "failed").order_by(IntegrationLog.id.desc()).limit(10)).all()
        recent_sync = self.db.execute(
            select(Integration.provider, Integration.last_synced_at).where(Integration.organization_id == self.org.id, Integration.last_synced_at.is_not(None))
            .order_by(Integration.last_synced_at.desc()).limit(5)).all()
        counted = [c for c in cards if c["status"] != "info"]
        return {
            "categories": [{"key": k, "title": t} for k, t in CATEGORIES],
            "cards": cards,
            "summary": {"total": len(counted), "connected": sum(c["status"] in ("connected", "active") for c in counted),
                        "failed": sum(c["status"] == "error" for c in counted),
                        "disconnected": sum(c["status"] in ("not_configured", "not_connected", "disabled", "untested") for c in counted)},
            "recent_errors": [{"integration": p, "action": a, "error": (e or "")[:300], "at": at} for a, e, at, p in recent_errors],
            "recent_sync": [{"integration": p, "at": at} for p, at in recent_sync],
            "redirects": {"google": gcal_redirect_uri(), "zoho": zoho_redirect_uri()},
            "google_ready": bool(runtime_settings().google_client_id and runtime_settings().google_client_secret),
        }

    def _builtin_cards(self) -> list[dict[str, Any]]:
        from app.core.storage import active_backend
        from app.models import APIKey, MessagingProviderConfig, WebhookEndpoint
        from app.services.organization_service import OrganizationService

        org_id = self.org.id
        cal = self.db.scalars(select(Integration).where(Integration.organization_id == org_id, Integration.provider == "google_calendar")).all()
        cal_ok = sum(1 for i in cal if i.status == IntegrationStatus.CONNECTED and i.is_enabled)
        cal_err = any(i.status == IntegrationStatus.ERROR for i in cal)
        zoom = self.db.scalar(select(Integration).where(Integration.organization_id == org_id, Integration.provider == "zoom"))
        msg = {r.channel: r for r in self.db.scalars(select(MessagingProviderConfig).where(MessagingProviderConfig.organization_id == org_id)).all()}
        hooks = self.db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.organization_id == org_id)).all()
        keys = self.db.scalar(select(func.count()).select_from(APIKey).where(APIKey.organization_id == org_id, APIKey.is_active.is_(True), APIKey.revoked_at.is_(None))) or 0
        booking = OrganizationService(self.db).get_settings(self.org, "general")["general"].get("booking_page_enabled", True)

        def b(key, name, category, description, status, link, account=None):
            return {"key": key, "name": name, "category": category, "description": description, "status": status, "enabled": status in ("connected", "active"),
                    "account": account, "last_synced_at": None, "last_error": None, "last_test": None, "syncs": [], "sync": {}, "docs": "", "privacy": "",
                    "builtin": True, "link": link, "can_manage": True}

        def channel(ch):
            r = msg.get(ch)
            if r is None:
                return "active", "Using the platform's account"
            if not r.enabled:
                return "disabled", None
            return ("connected" if r.last_test_ok else "error" if r.last_test_ok is False else "untested"), r.provider

        cards = [
            b("google_calendar", "Google Calendar", "google", "Each doctor's own Google Calendar: confirmed bookings appear as events, busy times block slots.",
              "error" if cal_err else "connected" if cal_ok else "not_configured", "/admin/integrations/calendar",
              f"{cal_ok} doctor{'s' if cal_ok != 1 else ''} connected" if cal_ok else None),
            b("google_meet", "Google Meet", "google", "A Meet link is created with the calendar event for online consultations and sent by email and WhatsApp.",
              "connected" if cal_ok else "not_configured", "/admin/integrations/calendar"),
            b("google_signin", "Sign in with Google", "google", "Patients and staff can sign in with their Google account (set up by the platform).",
              "active" if runtime_settings().google_client_id else "not_configured", None),
            b("zoom", "Zoom", "video", "Zoom meetings for online consultations (one Zoom account for the clinic).",
              "connected" if zoom and zoom.status == IntegrationStatus.CONNECTED and zoom.is_enabled else "error" if zoom and zoom.status == IntegrationStatus.ERROR else "not_configured",
              "/admin/integrations/calendar", zoom.external_account_id if zoom else None),
        ]
        for ch, name, cat in (("email", "Clinic email account (SMTP)", "email"), ("whatsapp", "WhatsApp Business account", "whatsapp"), ("sms", "SMS account (MSG91, Twilio)", "sms")):
            st, acct = channel(ch)
            cards.append(b(f"messaging_{ch}", name, cat, f"The clinic's own {ch.upper() if ch == 'sms' else ch} account for sign-in codes; otherwise the platform's.",
                           st, "/admin/settings/verification", acct))
        active_hooks = [h for h in hooks if h.is_active]
        cards += [
            b("templates", "Message templates", "email", "Text of confirmations, reminders, cancellations and payment messages (email, SMS, WhatsApp).", "active",
              "/admin/notifications"),
            b("shopify", "Shopify", "shopify", "Book Appointment buttons and a booking section for your Shopify theme (Liquid, no app).",
              "active" if booking else "disabled", "/admin/booking-page"),
            b("website", "WordPress, Wix, HTML, React", "website", "Copy-paste booking buttons, links with a preselected doctor or service, and an iframe widget.",
              "active" if booking else "disabled", "/admin/booking-page#websites"),
            b("api_keys", "API keys", "api", "Versioned REST API (/api/v1) with keys, permissions, rate limits, rotation, access logs and docs.",
              "active" if keys else "not_configured", "/admin/developers", f"{keys} active key{'s' if keys != 1 else ''}" if keys else None),
            b("webhooks", "Webhooks", "webhooks", "Signed event deliveries to your own systems, with retries, logs and safe redelivery.",
              "error" if any(h.disabled_at for h in hooks) else "active" if active_hooks else "not_configured", "/admin/developers",
              f"{len(active_hooks)} endpoint{'s' if len(active_hooks) != 1 else ''}" if active_hooks else None),
            {**b("platform_storage", "File storage", "storage", "Where uploaded files are kept. Set by the platform administrator.", "info", None,
                 "S3-compatible bucket" if active_backend() == "s3" else "This server's disk")},
        ]
        return cards

    # ------------------------------------------------------------------ detail
    def detail(self, key: str) -> dict[str, Any]:
        conn = self.connector(key)
        row = self.row(key)
        out = {**self.card(conn, row), "fields": self._fields(conn, row), "scopes": list(conn.scopes)}
        out["logs"] = [{"action": r.action, "status": r.status, "error": r.error, "duration_ms": r.duration_ms, "at": r.created_at} for r in self.db.scalars(
            select(IntegrationLog).where(IntegrationLog.integration_id == row.id).order_by(IntegrationLog.id.desc()).limit(50)).all()] if row else []
        out["problems"] = self.problems(row) if row else []
        if key == "n8n":
            out["incoming_url"] = f"{runtime_settings().frontend_url.rstrip('/')}/api/v1/automation/n8n/{row.public_id}" if row else None
            from app.connectors.n8n import ACTIONS
            from app.webhooks.catalog import EVENTS

            out["actions"] = ACTIONS
            out["events"] = {k: v for k, v in EVENTS.items() if k != "ping"}
        if conn.auth == "zoho":
            out["redirect_uri"] = zoho_redirect_uri()
        if conn.auth == "google":
            from app.integrations.google_calendar import redirect_uri

            out["redirect_uri"] = redirect_uri()
        return out

    def problems(self, row: Integration) -> list[dict[str, Any]]:
        rows = self.db.scalars(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == row.id, IntegrationSyncItem.status.in_(["failed", "dead"]))
                               .order_by(IntegrationSyncItem.updated_at.desc()).limit(50)).all()
        return [{"id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "status": r.status, "attempts": r.attempts, "error": r.last_error,
                 "next_attempt_at": r.next_attempt_at} for r in rows]

    # ------------------------------------------------------------------ changes
    def save(self, key: str, values: dict[str, Any], secrets: dict[str, str], clear: list[str]) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        specs: dict[str, F] = {f.name: f for f in conn.fields}
        row = self._ensure_row(conn)
        cfg = dict(row.config or {})
        hints = dict(cfg.get("_hints") or {})
        creds = Ctx(self.db, self.org, row).secrets()
        before = {k: v for k, v in cfg.items() if not k.startswith("_")}
        for name in clear:
            if name not in specs:
                raise ValidationFailed(f"Unknown setting {name}.", code="invalid_setting")
            cfg.pop(name, None)
            creds.pop(name, None)
            hints.pop(name, None)
        for name, raw in values.items():
            f = specs.get(name)
            if f is None or f.secret:
                raise ValidationFailed(f"Unknown setting {name}.", code="invalid_setting")
            if name == "max_attempts" and raw not in (None, ""):
                if not str(raw).isdigit() or not 1 <= int(raw) <= 20:
                    raise ValidationFailed("Retries must be between 1 and 20.", code="invalid_setting")
                cfg[name] = int(raw)
                continue
            coerced = _coerce(f, raw)
            if coerced is None:
                cfg.pop(name, None)
            else:
                cfg[name] = coerced
        changed_secret = False
        for name, raw in secrets.items():
            f = specs.get(name)
            if f is None or not f.secret:
                raise ValidationFailed(f"Unknown secret {name}.", code="invalid_setting")
            text = (raw or "").strip()
            if text:
                if len(text) > 4000 or any(ord(c) < 32 for c in text):
                    raise ValidationFailed(f"{f.label} is too long or contains invalid characters.", code="invalid_setting")
                creds[name], hints[name], changed_secret = text, _hint(text), True
        self._validate(conn, cfg)
        cfg["_hints"] = hints
        settings_changed = {k: v for k, v in cfg.items() if not k.startswith("_")} != before or changed_secret
        if settings_changed and conn.auth == "fields":
            cfg.pop("_last_test", None)  # test again with the new settings
            row.status = IntegrationStatus.DISCONNECTED
        if conn.auth == "zoho" and (changed_secret or "client_id" in values and values.get("client_id") != before.get("client_id")):
            for k in ("access_token", "refresh_token", "expires_at", "api_domain"):
                creds.pop(k, None)  # a different Zoho client: connect again
            row.status = IntegrationStatus.DISCONNECTED
            cfg.pop("_last_test", None)
        row.config = cfg
        Ctx(self.db, self.org, row).save_secrets(creds)
        shown = {}
        if key == "n8n":
            row.status = IntegrationStatus.DISCONNECTED if settings_changed else row.status
            shown = adapter_for(self.db, row).configure(self.actor, self.meta)  # type: ignore[attr-defined]
        self.db.flush()
        self._audit("integration.configured", row, before=before, after={"provider": key, "values": {k: v for k, v in cfg.items() if not k.startswith("_")},
                                                                          "secrets_changed": sorted(k for k, v in secrets.items() if v)})
        return {**self.detail(key), "shown_once": shown}

    def _validate(self, conn: registry.Connector, cfg: dict[str, Any]) -> None:
        if conn.key == "n8n" and cfg.get("url"):
            from app.webhooks.security import check_url

            if reason := check_url(cfg["url"]):
                raise ValidationFailed(reason, code="invalid_webhook_url")
        if conn.key == "ga4":
            from app.connectors.analytics import validate

            try:
                validate(cfg.get("measurement_id"), cfg.get("gtm_container_id"))
            except IntegrationAPIError as exc:
                raise ValidationFailed(str(exc), code="invalid_setting") from exc

    def set_enabled(self, key: str, enabled: bool) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self._ensure_row(conn)
        row.is_enabled = enabled
        if key == "n8n":
            ep = adapter_for(self.db, row).endpoint()  # type: ignore[attr-defined]
            if ep is not None:
                ep.is_active = enabled
        if not enabled:
            from sqlalchemy import update

            self.db.execute(update(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == row.id, IntegrationSyncItem.status.in_(["pending", "failed"]))
                            .values(status="skipped", last_error="Switched off"))
        self._audit("integration.enabled" if enabled else "integration.disabled", row, after={"provider": key})
        return self.detail(key)

    def test(self, key: str, to: str | None = None) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self.row(key)
        if row is None:
            raise ValidationFailed("Set it up first.", code="integration_not_configured")
        adapter = adapter_for(self.db, row)
        started = time.monotonic()
        try:
            message = adapter.test()
            if key == "gmail" and to:
                message = self._gmail_test(adapter, to)
            ok = True
        except IntegrationAPIError as exc:
            ok, message = False, str(exc)
        cfg = dict(row.config or {})
        cfg["_last_test"] = {"ok": ok, "message": message[:400], "at": utcnow().isoformat()}
        row.config = cfg
        if ok:
            row.status, row.last_error = IntegrationStatus.CONNECTED, None
        elif conn.auth == "fields" or row.status == IntegrationStatus.CONNECTED:
            row.status, row.last_error = IntegrationStatus.ERROR, message[:500]
        adapter.ctx.log("test", "ok" if ok else "failed", error=None if ok else message, started=started)
        self._audit("integration.tested", row, after={"provider": key, "ok": ok})
        self.db.flush()
        return {**self.detail(key), "test": cfg["_last_test"]}

    def _gmail_test(self, adapter, to: str) -> str:
        from app.notifications.providers import OutboundMessage

        if "@" not in to or len(to) > 254:
            raise IntegrationAPIError("Enter an email address for the test.")
        result = adapter.provider().send(OutboundMessage(channel="email", to=to.strip(), subject=f"Test email from {self.org.name}",
                                                         body="This test email was sent through your connected Gmail account.", from_name=self.org.name))
        if not result.ok:
            raise IntegrationAPIError(f"Gmail did not send it: {result.error}")
        return f"Test email sent to {to.strip()} from {adapter.ctx.integ.external_account_id}"

    def disconnect(self, key: str) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self.row(key)
        if row is None:
            raise NotFoundError("Not set up.")
        ctx = Ctx(self.db, self.org, row)
        creds = ctx.secrets()
        if conn.auth == "google" and creds.get("refresh_token"):
            from app.integrations import google_calendar as gcal

            gcal.revoke(creds["refresh_token"])
        if conn.auth == "zoho" and creds.get("refresh_token"):
            try:
                request("POST", f"{zoho_accounts(self._values(conn, row).get('data_center') or 'in')}/oauth/v2/token/revoke", params={"token": creds["refresh_token"]})
            except IntegrationAPIError:
                pass  # best effort; the token is deleted here regardless
        if key == "n8n":
            adapter_for(self.db, row).disconnect()  # type: ignore[attr-defined]
        keep = {k: creds[k] for k in ("client_secret",) if k in creds}  # Zoho: the clinic's own client stays for reconnecting
        ctx.save_secrets(keep)
        cfg = dict(row.config or {})
        cfg.pop("_last_test", None)
        if conn.auth != "zoho":
            cfg["_hints"] = {k: v for k, v in (cfg.get("_hints") or {}).items() if k in keep}
        row.config = cfg
        row.status, row.last_error, row.external_account_id = IntegrationStatus.DISCONNECTED, None, None
        from sqlalchemy import update

        self.db.execute(update(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == row.id, IntegrationSyncItem.status.in_(["pending", "failed"]))
                        .values(status="skipped", last_error="Disconnected"))
        self._audit("integration.disconnected", row, before={"provider": key})
        return self.detail(key)

    def rotate(self, key: str) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self.row(key)
        if key != "n8n" or row is None:
            raise ValidationFailed("For this integration, enter the new key in the settings and save.", code="rotate_not_supported")
        shown = adapter_for(self.db, row).rotate(self.actor, self.meta)  # type: ignore[attr-defined]
        self._audit("integration.secret_rotated", row, after={"provider": key})
        return {**self.detail(key), "shown_once": shown}

    def retry(self, key: str, item_id: int | None) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self.row(key)
        if row is None:
            raise NotFoundError("Not set up.")
        stmt = select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == row.id, IntegrationSyncItem.status.in_(["failed", "dead", "skipped"]))
        if item_id is not None:
            stmt = stmt.where(IntegrationSyncItem.id == item_id)
        now = utcnow()
        for item in self.db.scalars(stmt).all():
            item.status, item.attempts, item.next_attempt_at = "pending", 0, now
        self.db.flush()
        return self.detail(key)

    def sync_all(self, key: str) -> dict[str, Any]:
        conn = self.connector(key)
        self.require(conn)
        row = self.row(key)
        if row is None or self.status(conn, row) != "connected":
            raise ValidationFailed("Connect and test this integration first.", code="integration_not_connected")
        total = sum(enqueue_all(self.db, row, t) for t in conn.syncs if t != "appointment")
        self._audit("integration.full_sync_requested", row, after={"provider": key, "records": total})
        return {**self.detail(key), "queued": total}

    # ------------------------------------------------------------------ OAuth
    def oauth_start(self, key: str, return_to: str) -> str:
        conn = self.connector(key)
        self.require(conn)
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = f"/admin/integrations/{key}"
        row = self._ensure_row(conn)
        nonce = pysecrets.token_urlsafe(24)
        row.config = {**(row.config or {}), "_oauth_nonce_hash": hashlib.sha256(nonce.encode()).hexdigest()}
        s = runtime_settings()
        state = jwt.encode({"purpose": f"{conn.auth}_connector", "org": self.org.public_id, "integ": row.public_id, "user": self.actor.public_id if self.actor else None,
                            "nonce": nonce, "return_to": return_to, "exp": int(time.time()) + 600}, s.secret_key, algorithm=s.jwt_algorithm)
        if conn.auth == "google":
            from app.integrations import google_calendar as gcal

            if not gcal.configured():
                raise ValidationFailed("Google is not set up on this platform yet (Super admin → Integrations → Google).", code="google_not_configured")
            return gcal.authorization_url(state, scopes=["openid", "email", *conn.scopes])
        if conn.auth == "zoho":
            values = self._values(conn, row)
            if not values.get("client_id") or not Ctx(self.db, self.org, row).secrets().get("client_secret"):
                raise ValidationFailed("Enter and save the Zoho client ID and secret first.", code="zoho_client_missing")
            params = {"scope": ",".join(conn.scopes), "client_id": values["client_id"], "response_type": "code", "access_type": "offline",
                      "redirect_uri": zoho_redirect_uri(), "prompt": "consent", "state": state}
            return f"{zoho_accounts(values.get('data_center') or 'in')}/oauth/v2/auth?{urlencode(params)}"
        raise ValidationFailed("This integration does not use a sign-in.", code="no_oauth")


def _claims(db, state: str, purpose: str):
    s = runtime_settings()
    try:
        claims = jwt.decode(state, s.secret_key, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None, None, None
    if claims.get("purpose") != purpose:
        return None, None, None
    org = db.scalar(select(Organization).where(Organization.public_id == claims.get("org")))
    row = db.scalar(select(Integration).where(Integration.public_id == claims.get("integ"), Integration.organization_id == (org.id if org else -1)))
    if org is None or row is None:
        return claims, None, None
    expected = (row.config or {}).get("_oauth_nonce_hash")
    if not expected or not pysecrets.compare_digest(expected, hashlib.sha256(str(claims.get("nonce")).encode()).hexdigest()):
        return claims, None, None  # already used or superseded
    cfg = dict(row.config or {})
    cfg.pop("_oauth_nonce_hash", None)
    row.config = cfg
    return claims, org, row


def _finish(db, claims, org, row, account: str | None) -> None:
    actor = db.scalar(select(User).where(User.public_id == claims.get("user"))) if claims.get("user") else None
    row.status, row.last_error, row.is_enabled = IntegrationStatus.CONNECTED, None, True
    row.external_account_id, row.connected_at, row.connected_by_user_id = account, utcnow(), actor.id if actor else None
    cfg = dict(row.config or {})
    cfg["_last_test"] = {"ok": True, "message": f"Connected as {account}" if account else "Connected", "at": utcnow().isoformat()}
    row.config = cfg
    db.add(IntegrationLog(integration_id=row.id, direction="outbound", action="oauth.connect", status="ok", created_at=utcnow()))
    record_audit(db, action="integration.connected", actor=actor, organization_id=org.id, entity_type="integration", entity_id=row.public_id,
                 after={"provider": row.provider, "account": account})
    db.flush()


def google_connector_callback(db, *, code: str | None, state: str, error: str | None) -> tuple[str, str]:
    from app.integrations import google_calendar as gcal

    claims, org, row = _claims(db, state, "google_connector")
    return_to = (claims or {}).get("return_to") or "/admin/integrations"
    if row is None:
        return return_to, "invalid_state"
    if error or not code:
        return return_to, "denied"
    conn = registry.get(row.provider)
    try:
        tokens = gcal.exchange_code(code, required_scope=conn.scopes[0] if conn and conn.scopes else None)
        email = gcal.account_email(tokens["access_token"])
    except IntegrationAPIError as exc:
        row.status, row.last_error = IntegrationStatus.ERROR, str(exc)[:500]
        db.add(IntegrationLog(integration_id=row.id, direction="outbound", action="oauth.connect", status="failed", error=str(exc)[:1000], created_at=utcnow()))
        return return_to, "failed"
    Ctx(db, org, row).save_secrets({"refresh_token": tokens["refresh_token"], "access_token": tokens["access_token"], "expires_at": tokens["expires_at"]})
    _finish(db, claims, org, row, email)
    return return_to, "connected"


def zoho_connector_callback(db, *, code: str | None, state: str, error: str | None, accounts_server: str | None) -> tuple[str, str]:
    claims, org, row = _claims(db, state, "zoho_connector")
    return_to = (claims or {}).get("return_to") or "/admin/integrations"
    if row is None:
        return return_to, "invalid_state"
    if error or not code:
        return return_to, "denied"
    ctx = Ctx(db, org, row)
    values, creds = ctx.config, ctx.secrets()
    dc = values.get("data_center") or "in"
    host = urlparse(accounts_server or "").hostname or ""
    if host.startswith("accounts.zoho.") and host[len("accounts.zoho."):] in registry.ZOHO_DATA_CENTERS:
        dc = host[len("accounts.zoho."):]  # Zoho says which data centre the account lives in
        row.config = {**(row.config or {}), "data_center": dc}
    try:
        tokens = zoho_token_request(dc, {"code": code, "grant_type": "authorization_code", "client_id": values.get("client_id") or "",
                                         "client_secret": creds.get("client_secret", ""), "redirect_uri": zoho_redirect_uri()})
        if not tokens.get("refresh_token"):
            raise IntegrationAPIError("Zoho did not return a refresh token. Remove the app's access in Zoho and connect again.")
    except IntegrationAPIError as exc:
        row.status, row.last_error = IntegrationStatus.ERROR, str(exc)[:500]
        db.add(IntegrationLog(integration_id=row.id, direction="outbound", action="oauth.connect", status="failed", error=str(exc)[:1000], created_at=utcnow()))
        return return_to, "failed"
    creds.update(refresh_token=tokens["refresh_token"], access_token=tokens["access_token"], expires_at=tokens["expires_at"],
                 api_domain=tokens.get("api_domain") or f"https://www.zohoapis.{dc}")
    ctx.save_secrets(creds)
    row.status = IntegrationStatus.CONNECTED
    account = None
    try:
        account = adapter_for(db, row).test()
    except IntegrationAPIError as exc:
        row.status, row.last_error = IntegrationStatus.ERROR, str(exc)[:500]
        return return_to, "failed"
    _finish(db, claims, org, row, account.replace("Connected as ", "").replace("Connected to ", "")[:255])
    return return_to, "connected"


def gmail_sender(db, org_id: int):
    """The clinic's Gmail, if connected and set to send all clinic emails (used by notifications and sign-in codes)."""
    row = db.scalar(select(Integration).where(Integration.organization_id == org_id, Integration.provider == "gmail", Integration.is_enabled.is_(True),
                                              Integration.status == IntegrationStatus.CONNECTED))
    if row is None or not {**registry.CONNECTORS["gmail"].defaults, **(row.config or {})}.get("use_for_all"):
        return None
    return adapter_for(db, row).provider()  # type: ignore[attr-defined]

