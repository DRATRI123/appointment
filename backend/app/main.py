"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import app.core.branch_scope  # noqa: F401  (registers the branch isolation filter)
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.observability import MetricsMiddleware, init_sentry, metrics_response
from app.core.storage import media_from_bucket
from app.security.headers import RequestIDMiddleware, SecurityHeadersMiddleware
from app.security.rate_limit import limiter
from app.workers import jobs  # noqa: F401  (registers background jobs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app")
    settings: Settings = app.state.settings
    if settings.worker_threads:
        # Sync endpoints run in this many threads per process. More threads than this only queue for Python's single
        # interpreter lock (measured on SQLite at 100 users); a request never holds the database lock while waiting
        # for one (see get_db), so a small pool cannot deadlock.
        import anyio.to_thread

        anyio.to_thread.current_default_thread_limiter().total_tokens = settings.worker_threads
    log.info("app.start", env=settings.app_env, version=settings.app_version, sqlite=settings.is_sqlite, worker_threads=settings.worker_threads)
    yield
    log.info("app.stop")


log = get_logger("app")


class SavingPausedMiddleware:
    """While the super admin moves or updates the database (Super admin → Database), refuse anything that would
    save, with a friendly "back in a few minutes". Reading keeps working, and so do sign-in and the Database page."""

    def __init__(self, app, api_prefix: str):
        self.app, self.prefix = app, api_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            path = scope.get("path", "")
            if path.startswith(self.prefix) and not path.startswith((f"{self.prefix}/platform/database", f"{self.prefix}/auth/")):
                from app.ops.db_move import saving_paused

                if saving_paused():
                    from starlette.responses import JSONResponse

                    response = JSONResponse({"detail": "We are upgrading the system. Please try again in a few minutes.", "code": "maintenance"},
                                            status_code=503, headers={"Retry-After": "120"})
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def commit_in_handler(app: FastAPI) -> None:
    """Commit each sync endpoint's request session in the endpoint's own worker thread, right after it returns.

    Write requests also take the database's write lock only here, when the endpoint starts (see get_db).
    FastAPI validates a sync endpoint's response in a second worker thread, and the session used to be committed only
    after that. On SQLite a writer then held the database's single write lock while waiting for a thread, and under
    load every thread was taken by requests waiting for that lock: nothing moved until SQLite gave up after 30 s
    (measured at 100 users). Committing here releases the lock before any other thread is needed. A commit error now
    also becomes the request's error response instead of surfacing after the handler finished."""
    import functools
    import inspect

    from fastapi.routing import APIRoute
    from sqlalchemy.orm import Session

    def wrap(call):
        @functools.wraps(call)
        def run(*args, **kwargs):
            from app.core.database import begin_writing

            for value in kwargs.values():
                if isinstance(value, Session) and value.info.pop("write_lock_in_handler", False):
                    begin_writing(value)
            result = call(*args, **kwargs)
            for value in kwargs.values():
                if isinstance(value, Session) and value.info.get("commit_in_handler"):
                    value.commit()
            return result
        run.commits_in_handler = True
        return run

    def patch(routes) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                if not inspect.iscoroutinefunction(route.endpoint) and not getattr(route.endpoint, "commits_in_handler", False):
                    route.endpoint = wrap(route.endpoint)
                    route.dependant.call = route.endpoint
            elif getattr(route, "original_router", None) is not None:  # an included router (built lazily by FastAPI)
                patch(route.original_router.routes)

    patch(app.router.routes)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.limiter = limiter

    # Middleware order: outermost first. Request id must wrap everything so errors carry it.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token", "X-Organization-Id", "X-API-Key", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Idempotent-Replayed"],
    )
    if settings.trusted_hosts and settings.trusted_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    if settings.rate_limit_enabled:
        app.add_middleware(SlowAPIMiddleware)
        def _limited(request, exc):
            from app.core.observability import security_event

            security_event("rate_limited")
            return _rate_limit_exceeded_handler(request, exc)

        app.add_exception_handler(RateLimitExceeded, _limited)
    app.add_middleware(SavingPausedMiddleware, api_prefix=settings.api_v1_prefix)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(MetricsMiddleware)  # outermost: times everything, including errors
    init_sentry(settings)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    commit_in_handler(app)
    # Prometheus scrape endpoint, outside /api so the public web app never proxies it.
    app.add_route("/metrics", metrics_response, include_in_schema=False)


    # Public uploads (logos, photos, service images). Private files are never served from here.
    # One route for both storages, so switching between this server's disk and S3 in the panel needs no restart.
    (Path(settings.storage_local_path) / "public").mkdir(parents=True, exist_ok=True)
    app.add_route("/media/{path:path}", media_from_bucket, methods=["GET", "HEAD"], include_in_schema=False)
    return app


app = create_app()
