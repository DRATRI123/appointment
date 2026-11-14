from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DB, AppSettings
from app.core.observability import migration_head, storage_writable
from app.schemas.common import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
def health(settings: AppSettings) -> HealthStatus:
    return HealthStatus(
        status="ok", app=settings.app_name, version=settings.app_version, environment=settings.app_env
    )


@router.get("/health/ready", response_model=HealthStatus, summary="Readiness probe")
def readiness(db: DB, settings: AppSettings, response: Response) -> HealthStatus:
    """Ready to serve traffic: database reachable, schema migrated to this release, upload storage writable.

    Worker, backlog and backup problems do not make the API unready (it can still take bookings); they are reported
    by /metrics and the platform System status page instead."""
    checks: dict[str, str] = {}
    try:
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["database"] = "ok"
        head = migration_head()
        checks["migrations"] = "ok" if current == head else f"pending: database at {current}, release needs {head}"
    except Exception as exc:  # database down, or never migrated
        checks["database"] = f"error: {exc.__class__.__name__}"
    checks["storage"] = "ok" if storage_writable(settings) else "error: upload folder is not writable"
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(
        status="ok" if healthy else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="sqlite" if settings.is_sqlite else "postgresql",
        checks=checks,
    )
