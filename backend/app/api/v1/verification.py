"""Settings → OTP & verification: the clinic's delivery accounts and test sends. The policy itself is the "otp"
settings namespace (PUT /organizations/{id}/settings/otp)."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.security.rate_limit import limiter
from app.services.otp.provider_settings import ProviderSettingsService

router = APIRouter(prefix="/verification", tags=["verification"])

Reader = Annotated[TenantContext, Depends(require_permission("organization:read"))]
Writer = Annotated[TenantContext, Depends(require_permission("organization:write"))]


class ProviderSave(BaseModel):
    provider: str = Field(max_length=32)
    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict, description="Only the secrets you change; empty values keep the stored ones")


class TestSend(BaseModel):
    destination: str = Field(min_length=3, max_length=254)


@router.get("", summary="Verification policy, channel accounts (no secrets) and provider field definitions")
def overview(db: DB, ctx: Reader, meta: Meta):
    return ProviderSettingsService(db, ctx.organization, ctx.user, meta).overview()


@router.put("/providers/{channel}", summary="Set up the clinic's own account for a channel")
def save_provider(channel: str, body: ProviderSave, db: DB, ctx: Writer, meta: Meta):
    return ProviderSettingsService(db, ctx.organization, ctx.user, meta).save(channel, provider=body.provider, enabled=body.enabled,
                                                                                 settings=body.settings, secrets=body.secrets)


@router.delete("/providers/{channel}", summary="Remove the clinic's own account (the platform account is used, if any)")
def remove_provider(channel: str, db: DB, ctx: Writer, meta: Meta):
    return ProviderSettingsService(db, ctx.organization, ctx.user, meta).remove(channel)


@router.post("/providers/{channel}/test", summary="Send a sample code to check the account works")
@limiter.limit("5/minute;30/hour")
def test_provider(request: Request, response: Response, channel: str, body: TestSend, db: DB, ctx: Writer, meta: Meta):
    return ProviderSettingsService(db, ctx.organization, ctx.user, meta).test(channel, body.destination)
