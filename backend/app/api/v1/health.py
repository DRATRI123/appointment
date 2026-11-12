from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DB, AppSettings
from app.schemas.common import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
def health(settings: AppSettings) -> HealthStatus:
    return HealthStatus(
        status="ok", app=settings.app_name, version=settings.app_version, environment=settings.app_env
    )


@router.get("/health/ready", response_model=HealthStatus, summary="Readiness probe")
def readiness(db: DB, settings: AppSettings, response: Response) -> HealthStatus:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        overall = "ok"
    except Exception as exc:  # pragma: no cover - only when the database is down
        checks["database"] = f"error: {exc.__class__.__name__}"
        overall = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(
        status=overall,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="sqlite" if settings.is_sqlite else "postgresql",
        checks=checks,
    )
