"""Background worker: ``python -m app.workers.runner [--once] [--interval 20]``.

Runs every periodic job in turn, then sleeps. Each cycle writes a heartbeat and each job's outcome (duration,
result or error) to ``system_settings``, which the health checks, ``/metrics`` and the platform System status page
read. SIGTERM / Ctrl+C finishes the job in progress and exits cleanly, so container restarts never cut a job short.
"""
from __future__ import annotations

import argparse
import signal
import time

from app.core.database import session_scope
from app.core.logging import configure_logging, get_logger
from app.services import ops_service
from app.workers import jobs
from app.workers.queue import get_job

log = get_logger(__name__)


class Runner:
    def __init__(self, interval: int = 60):
        self.interval = interval
        self.stopping = False

    def stop(self, *_args) -> None:
        if not self.stopping:
            log.info("worker.stopping")
        self.stopping = True

    def _record(self, fn, *args, **kwargs) -> None:
        # Bookkeeping must never take the worker down (e.g. the database is briefly unavailable).
        try:
            with session_scope() as db:
                fn(db, *args, **kwargs)
        except Exception:
            log.exception("worker.record_failed")

    def run_job(self, name: str) -> bool:
        started = time.perf_counter()
        try:
            result = get_job(name)()
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            log.exception("jobs.failed", job=name, duration_ms=duration)
            self._record(ops_service.record_job, name, ok=False, duration_ms=duration, error=f"{type(exc).__name__}: {exc}")
            return False
        duration = int((time.perf_counter() - started) * 1000)
        self._record(ops_service.record_job, name, ok=True, duration_ms=duration, result=result)
        return True

    def run_cycle(self) -> dict[str, bool]:
        self._record(ops_service.record_heartbeat, interval_seconds=self.interval)
        outcome: dict[str, bool] = {}
        for name in jobs.PERIODIC_JOBS:
            if self.stopping:
                break
            outcome[name] = self.run_job(name)
        return outcome

    def sleep(self) -> None:
        deadline = time.monotonic() + self.interval
        while not self.stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    def forever(self) -> None:
        log.info("worker.start", interval=self.interval, jobs=list(jobs.PERIODIC_JOBS))
        while not self.stopping:
            self.run_cycle()
            self.sleep()
        log.info("worker.stopped")


def run_all() -> dict[str, bool]:
    """One cycle; kept for scripts that imported it."""
    return Runner().run_cycle()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run every job once and exit (non-zero if any failed)")
    parser.add_argument("--interval", type=int, default=60, help="seconds to sleep between cycles")
    args = parser.parse_args(argv)
    configure_logging()
    runner = Runner(interval=args.interval)
    signal.signal(signal.SIGTERM, runner.stop)
    signal.signal(signal.SIGINT, runner.stop)
    if args.once:
        return 0 if all(runner.run_cycle().values()) else 1
    runner.forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
