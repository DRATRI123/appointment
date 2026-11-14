from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, AppSettings
from app.core.enums import AppointmentStatus, PaymentStatus, SystemRole
from app.security.permissions import PERMISSIONS

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/", summary="Public application metadata")
def meta(settings: AppSettings) -> dict:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "api_prefix": settings.api_v1_prefix,
        "currency": "INR",
        "money_unit": "paise",
    }


@router.get("/enums", summary="Enumerations used by the frontend")
def enums() -> dict:
    return {
        "appointment_statuses": [s.value for s in AppointmentStatus],
        "payment_statuses": [s.value for s in PaymentStatus],
        "system_roles": [r.value for r in SystemRole],
        "permissions": sorted(PERMISSIONS),
    }


@router.get("/platform", summary="Public platform settings: name, support email, sign-up switch and announcement")
def platform(db: DB) -> dict:
    from app.services.platform_service import public_platform

    return public_platform(db).model_dump()
