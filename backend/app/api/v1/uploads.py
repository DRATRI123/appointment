"""Image uploads for logos, profile photos and service images (public files)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import AppSettings, TenantContext, get_tenant_context
from app.core.exceptions import PermissionDenied
from app.core.storage import get_storage, validate_upload
from app.schemas.catalog import UploadResponse

router = APIRouter(prefix="/uploads", tags=["uploads"])

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
WRITE_PERMISSIONS = ("organization:write", "branches:write", "professionals:write", "services:write", "upi_accounts:write")


@router.post("/images", response_model=UploadResponse, summary="Upload a public image (PNG/JPEG/WebP, max 5 MB)")
async def upload_image(
    settings: AppSettings,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    file: UploadFile = File(...),
) -> UploadResponse:
    if not any(ctx.has(p) for p in WRITE_PERMISSIONS):
        raise PermissionDenied("You cannot upload files for this organization.", code="permission_denied")
    data = await file.read()
    mime = validate_upload(data, allowed=IMAGE_TYPES, max_mb=settings.max_upload_size_mb)
    stored = get_storage().save(scope=f"org/{ctx.organization.public_id}", visibility="public", data=data, mime_type=mime)
    return UploadResponse(url=stored.url or "", key=stored.key, mime_type=stored.mime_type, size_bytes=stored.size_bytes)
