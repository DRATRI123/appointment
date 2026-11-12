"""Minimal job queue abstraction.

Phase 1 ships an inline runner (jobs execute immediately in-process). Later phases add an ARQ/Celery
backend behind the same interface so services never depend on a specific queue library.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

JobFunc = Callable[..., Any]
_REGISTRY: dict[str, JobFunc] = {}


def job(name: str) -> Callable[[JobFunc], JobFunc]:
    """Register a function as a named background job."""

    def decorator(func: JobFunc) -> JobFunc:
        _REGISTRY[name] = func
        return func

    return decorator


def get_job(name: str) -> JobFunc:
    try:
        return _REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - programming error
        raise LookupError(f"Unknown job: {name}") from exc


class JobQueue(Protocol):
    def enqueue(self, name: str, *, run_at: datetime | None = None, **kwargs: Any) -> str: ...


class InlineJobQueue:
    """Executes jobs synchronously. Suitable for development, tests and single-instance deployments."""

    def enqueue(self, name: str, *, run_at: datetime | None = None, **kwargs: Any) -> str:
        func = get_job(name)
        log.info("job.run_inline", job=name, run_at=run_at)
        func(**kwargs)
        return f"inline:{name}"


def get_queue() -> JobQueue:
    settings = get_settings()
    if settings.job_backend == "inline":
        return InlineJobQueue()
    raise NotImplementedError(f"Job backend not available yet: {settings.job_backend}")
