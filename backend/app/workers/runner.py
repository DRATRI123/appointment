"""Simple periodic runner: ``python -m app.workers.runner [--once] [--interval 60]``.

Production deployments replace this with ARQ/Celery beat through the same job registry.
"""
from __future__ import annotations

import argparse
import time

from app.core.logging import configure_logging, get_logger
from app.workers import jobs
from app.workers.queue import get_job


def run_all() -> None:
    for name in jobs.PERIODIC_JOBS:
        try:
            get_job(name)()
        except Exception:  # pragma: no cover - keep the loop alive
            get_logger(__name__).exception("jobs.failed", job=name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    configure_logging()
    while True:
        run_all()
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
