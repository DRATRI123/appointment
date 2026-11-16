"""Monitoring: Prometheus metrics, schema/storage readiness checks and optional Sentry error tracking.

* ``GET /metrics`` (outside /api, never proxied by the web app) serves Prometheus text format. It is disabled
  unless METRICS_TOKEN is set, and then requires ``Authorization: Bearer <METRICS_TOKEN>``.
* Request metrics use the route *template* (``/api/v1/appointments/{appointment_id}``), never the raw path, so IDs
  and personal data never become label values.
* Operational gauges (worker heartbeat age, job failures, backlog, last backup) are read from the database at
  scrape time, so every API process reports the same numbers.
* Sentry is enabled only with SENTRY_DSN. Request bodies, cookies, auth headers, query strings and user details are
  removed before an event leaves the server.
"""
from __future__ import annotations

import hmac
import os
import tempfile
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import BASE_DIR, Settings, get_settings
from app.core.logging import get_logger
from app.core.time import utcnow

log = get_logger(__name__)

REGISTRY = CollectorRegistry(auto_describe=True)
REQUESTS = Counter("app_http_requests_total", "HTTP requests handled", ("method", "route", "status"), registry=REGISTRY)
LATENCY = Histogram("app_http_request_duration_seconds", "Time to produce a response", ("method", "route"), registry=REGISTRY,
                    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))


# Security events, counted by kind (never with user, IP or values as labels: only the kind of event). Prometheus alert
# rules (deployment/monitoring/alerts.yml) watch for bursts: password guessing, code guessing, scraping, payment fraud.
SECURITY_EVENTS = Counter("app_security_events_total", "Refused or suspicious requests by kind", ("event",), registry=REGISTRY)
_SECURITY_CODES = {
    "invalid_credentials": "login_failed", "account_locked": "login_locked", "mfa_code_invalid": "mfa_failed",
    "otp_incorrect": "otp_failed", "otp_locked": "otp_locked", "otp_destination_limit": "otp_rate_limited",
    "otp_ip_limit": "otp_rate_limited", "otp_session_limit": "otp_rate_limited", "otp_cooldown": "otp_rate_limited",
    "rate_limited": "rate_limited", "invalid_api_key": "api_key_invalid", "ip_not_allowed": "ip_blocked",
    "csrf_failed": "csrf_failed", "permission_denied": "access_denied", "platform_admin_required": "access_denied",
    "not_a_member": "access_denied", "wrong_organization": "access_denied", "api_key_not_allowed": "access_denied",
    # nosec B105 on the next line: "token_invalid" is a metric label (an error code name), not a password.
    "duplicate_utr": "payment_duplicate_utr", "token_invalid": "token_invalid", "refresh_reused": "refresh_token_reused",  # nosec B105
    "maintenance": "maintenance",
}


def security_event(event: str) -> None:
    SECURITY_EVENTS.labels(event=event).inc()


def security_event_for_code(code: str | None) -> None:
    if code and (event := _SECURITY_CODES.get(code)):
        security_event(event)


def _route_template(scope: Scope) -> str:
    """The matched route pattern with its full prefix, e.g. /api/v1/branches/{branch_id}. Unmatched paths share one
    label so random URLs cannot create unlimited time series."""
    path = scope.get("path", "")
    template = getattr(scope.get("route"), "path", None)
    if template is None:
        return "/media" if path.startswith("/media/") else "unmatched"
    prefix = get_settings().api_v1_prefix
    if path.startswith(prefix + "/") and not template.startswith(prefix):
        template = prefix + template  # routers included under the API prefix report their own relative pattern
    return template


class MetricsMiddleware:
    """Pure ASGI middleware (no response buffering), counting requests by route template and status class."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 500}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            template = _route_template(scope)
            method = scope.get("method", "GET")
            REQUESTS.labels(method, template, f"{status['code'] // 100}xx").inc()
            LATENCY.labels(method, template).observe(time.perf_counter() - started)


def _age_seconds(iso: str | None) -> float:
    if not iso:
        return -1.0
    return max(0.0, (utcnow() - datetime.fromisoformat(iso)).total_seconds())


class OpsCollector:
    """Reads the operational status at scrape time. A database outage shows up as app_up 0, never as a crash."""

    def collect(self):
        from app.core.database import session_scope
        from app.services.ops_service import system_status

        up = GaugeMetricFamily("app_ops_status_up", "1 if the operational status could be read from the database")
        try:
            with session_scope() as db:
                st = system_status(db)
        except Exception:
            log.exception("metrics.status_failed")
            up.add_metric([], 0)
            yield up
            return
        up.add_metric([], 1)
        yield up
        g = GaugeMetricFamily("app_worker_heartbeat_age_seconds", "Seconds since the background worker last reported (-1 = never)")
        g.add_metric([], _age_seconds(st["worker"]["last_heartbeat_at"]))
        yield g
        fails = GaugeMetricFamily("app_job_consecutive_failures", "Consecutive failed runs per background job", labels=["job"])
        last_ok = GaugeMetricFamily("app_job_last_success_age_seconds", "Seconds since each job last succeeded (-1 = never)", labels=["job"])
        for name, job in sorted(st["jobs"].items()):
            fails.add_metric([name], float(job.get("consecutive_failures", 0)))
            last_ok.add_metric([name], _age_seconds(job.get("last_success_at")))
        yield fails
        yield last_ok
        backlog = GaugeMetricFamily("app_backlog", "Work waiting: due messages, webhook deliveries, payments to verify", labels=["kind"])
        for kind, value in st["backlog"].items():
            backlog.add_metric([kind], float(value))
        yield backlog
        b_age = GaugeMetricFamily("app_backup_last_age_seconds", "Seconds since the last backup attempt (-1 = never)")
        b_age.add_metric([], _age_seconds(st["backup"].get("at")))
        yield b_age
        b_ok = GaugeMetricFamily("app_backup_last_ok", "1 if the last backup attempt succeeded and is recent")
        b_ok.add_metric([], 1.0 if st["backup"]["ok"] else 0.0)
        yield b_ok


REGISTRY.register(OpsCollector())

_multiprocess_registry: CollectorRegistry | None = None


def _exposition_registry() -> CollectorRegistry:
    """With several API worker processes (PROMETHEUS_MULTIPROC_DIR set), request metrics are shared through files so a
    scrape sees the sum over all processes, not whichever process happened to answer."""
    global _multiprocess_registry
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return REGISTRY
    if _multiprocess_registry is None:
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        registry.register(OpsCollector())
        _multiprocess_registry = registry
    return _multiprocess_registry


def metrics_response(request: Request) -> Response:
    settings = get_settings()
    if not settings.metrics_token:
        return Response(status_code=404)
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {settings.metrics_token}".encode()):
        return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(generate_latest(_exposition_registry()), media_type=CONTENT_TYPE_LATEST, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------------------------------------- readiness
@lru_cache
def migration_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def storage_writable(settings: Settings) -> bool:
    from app.core.storage import active_backend

    if active_backend() != "local":
        return True  # S3 reachability is reported by uploads themselves; no write on every probe
    root = Path(settings.storage_local_path)
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".probe-", delete=True) as fh:
            fh.write(b"ok")
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------------------------- Sentry
_SCRUB_HEADERS = {"authorization", "cookie", "x-api-key", "x-csrf-token", "set-cookie"}


def scrub_event(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """Remove anything that could identify a patient or authenticate as someone before sending to Sentry."""
    req = event.get("request")
    if isinstance(req, dict):
        req.pop("data", None)
        req.pop("cookies", None)
        req.pop("query_string", None)
        headers = req.get("headers")
        if isinstance(headers, dict):
            req["headers"] = {k: ("[removed]" if k.lower() in _SCRUB_HEADERS else v) for k, v in headers.items()}
    event.pop("user", None)
    for exc in (event.get("exception") or {}).get("values", []) or []:
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            frame.pop("vars", None)  # local variables can hold names, mobiles, UTRs
    return event


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=os.environ.get("APP_RELEASE") or settings.app_version,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub_event,
    )
    return True
