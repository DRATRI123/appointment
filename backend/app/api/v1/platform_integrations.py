"""Super admin → Integrations: platform settings from the panel or .env, connection tests, storage switch, .env export."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import DB, Meta, PlatformAdmin, recent_auth
from app.core.database import writes_on_read
from app.core.exceptions import ValidationFailed
from app.security.rate_limit import limiter
from app.services import platform_config as pc
from app.services import storage_migration as sm
from app.services.audit_service import record_audit

router = APIRouter(prefix="/platform/integrations", tags=["platform"])


class SectionSave(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict, description="Empty strings keep the stored secret")
    clear: list[str] = Field(default_factory=list, description="Fields to remove from the panel, so the .env value applies again")


class TestRequest(BaseModel):
    to: str | None = Field(default=None, max_length=200, description="Email address or mobile number for message providers")


class StorageSwitch(BaseModel):
    target: str = Field(description="local or s3")


def _overview(db) -> dict[str, Any]:
    from app.core.storage import active_backend
    from app.integrations.google_calendar import redirect_uri
    from app.services.platform_config import runtime_settings

    row = pc.read_row(db)
    sections = [pc.section_state(db, key, row) for key in pc.SECTIONS]
    base = runtime_settings().frontend_url.rstrip("/")
    return {
        "sections": sections,
        "storage": {"active": active_backend(), "fallback": pc.overrides().get("storage_previous_backend"), "migration": sm.state(db)},
        "google": {"calendar_redirect_uri": redirect_uri(), "javascript_origin": base,
                   "sign_in_enabled": bool(runtime_settings().google_client_id)},
        "whatsapp_webhook_url": f"{base}/api/v1/webhooks/whatsapp",
        "environment": runtime_settings().app_env,
        "summary": {"total": len(sections), "connected": sum(s["status"] == "connected" for s in sections),
                    "errors": sum(s["status"] == "error" for s in sections),
                    "not_configured": sum(s["status"] == "not_configured" for s in sections)},
    }


@router.get("", summary="Platform integration settings, where each value comes from (panel, .env, default) and their status")
def overview(db: DB, _: PlatformAdmin) -> dict[str, Any]:
    return _overview(db)


@router.put("/{section}", summary="Save a section (secrets encrypted; panel values win over .env)", dependencies=[recent_auth("platform")])
def save(section: str, payload: SectionSave, db: DB, admin: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    pc.save_section(db, section, payload.values, payload.secrets, payload.clear)
    if section == "storage":
        from app.core.storage import reset_storage

        reset_storage()
    # Audit names only: never secret values.
    record_audit(db, action="platform.integration_saved", actor=admin, entity_type="platform_integration", entity_id=section,
                 after={"values": {k: v for k, v in payload.values.items()}, "secrets_changed": sorted(k for k, v in payload.secrets.items() if v),
                        "cleared": payload.clear}, meta=meta)
    return _overview(db)


@router.post("/{section}/test", summary="Test the saved settings for real (write/read a file, ask Google, send a message)")
@limiter.limit("10/minute")
def test(request: Request, section: str, payload: TestRequest, db: DB, admin: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    from app.services import platform_tests

    if section not in pc.SECTIONS:
        raise ValidationFailed("Unknown section.", code="invalid_section")
    state = pc.section_state(db, section)
    if state["missing"]:
        raise ValidationFailed("Fill in first: " + ", ".join(state["missing"]) + ".", code="section_incomplete")
    ok, message = platform_tests.run(section, payload.model_dump())
    result = pc.record_test(db, section, ok, message)
    record_audit(db, action="platform.integration_tested", actor=admin, entity_type="platform_integration", entity_id=section,
                 after={"ok": ok, "message": message[:200]}, meta=meta)
    return {**result, "overview": _overview(db)}


@router.post("/storage/switch", summary="Copy every file to the other storage, check each copy, then switch", dependencies=[recent_auth("platform")])
def storage_switch(payload: StorageSwitch, db: DB, admin: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    st = sm.request_switch(db, payload.target, admin.id)
    record_audit(db, action="platform.storage_switch_requested", actor=admin, entity_type="platform_integration", entity_id="storage",
                 after={"source": st["source"], "target": st["target"]}, meta=meta)
    return _overview(db)


@router.post("/storage/finish", summary="Stop reading missing files from the previous storage", dependencies=[recent_auth("platform")])
def storage_finish(db: DB, admin: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    sm.finish(db)
    record_audit(db, action="platform.storage_switch_finished", actor=admin, entity_type="platform_integration", entity_id="storage", meta=meta)
    return _overview(db)


@router.get("/storage/usage", summary="Files and bytes in the active storage")
def storage_usage(db: DB, _: PlatformAdmin) -> dict[str, Any]:
    return sm.usage(db)


@router.get("/env", response_class=PlainTextResponse, summary="The panel values as .env lines (secrets only on request)")
@writes_on_read  # audit-logged
def env_export(request: Request, db: DB, admin: PlatformAdmin, meta: Meta, include_secrets: bool = Query(default=False)) -> PlainTextResponse:
    if include_secrets:
        from app.services.privacy_service import require_recent_auth

        require_recent_auth(db, request, None, action="platform")
    text = pc.env_lines(db, include_secrets)
    record_audit(db, action="platform.integration_env_exported", actor=admin, entity_type="platform_integration", entity_id="env",
                 after={"include_secrets": include_secrets}, meta=meta)
    return PlainTextResponse(text, headers={"Content-Disposition": 'attachment; filename="integrations.env"', "Cache-Control": "no-store"})


@router.post("/env/write", summary="Development computer only: also write the panel values into backend/.env",
             dependencies=[recent_auth("platform")])
def env_write(db: DB, admin: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    result = pc.write_env_file(db)
    record_audit(db, action="platform.integration_env_written", actor=admin, entity_type="platform_integration", entity_id="env",
                 after={"variables": result["written"]}, meta=meta)
    return result


@router.get("/whatsapp/templates", summary="Approved WhatsApp message templates of the platform's WhatsApp Business Account")
def whatsapp_templates(db: DB, _: PlatformAdmin) -> list[dict[str, Any]]:
    from app.integrations.http import IntegrationAPIError, check, request
    from app.services.platform_config import runtime_settings

    s = runtime_settings()
    if not (s.whatsapp_business_account_id and s.whatsapp_cloud_token):
        raise ValidationFailed("Enter the WhatsApp Business Account ID and the access token first.", code="section_incomplete")
    try:
        data = check(request("GET", f"https://graph.facebook.com/{s.whatsapp_cloud_api_version}/{s.whatsapp_business_account_id}/message_templates",
                             params={"fields": "name,language,status,category", "limit": 200}, headers={"Authorization": f"Bearer {s.whatsapp_cloud_token}"}),
                     "WhatsApp templates")
    except IntegrationAPIError as exc:
        raise ValidationFailed(str(exc), code="whatsapp_error") from exc
    return [{"name": t.get("name"), "language": t.get("language"), "status": t.get("status"), "category": t.get("category")} for t in data.get("data", [])]
