"""Regression test for a stall measured at 100 users on SQLite.

Every request used to take SQLite's single write lock (BEGIN IMMEDIATE), even reads, and released it only after
FastAPI had validated the response, which for sync endpoints needs a second worker thread. When every worker thread
was busy waiting for the lock, the request holding it waited for a thread: nothing moved until SQLite gave up after
30 s with "database is locked". Now reads take no lock and writers commit in their own thread before the response
is built. Dependencies (FastAPI runs each in its own thread too) only read; the endpoint takes the lock. This test
squeezes the worker pool to 3 threads and sends many writes and reads at once.
"""
from __future__ import annotations

import asyncio
import time
from typing import Annotated

import anyio.to_thread
import httpx
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import app.core.database as database
from app.api.deps import DB
from app.core.config import Settings
from app.main import commit_in_handler, create_app


class Out(BaseModel):  # a response model, so FastAPI validates the response in a worker thread
    n: int


def _who(db: DB) -> int:
    """Like "who is signed in": a dependency that reads the database before the endpoint runs."""
    return db.execute(text("SELECT COUNT(*) FROM probe")).scalar_one()


def _app():
    app = create_app()

    def write(db: DB, _seen: Annotated[int, Depends(_who)]) -> Out:
        db.execute(text("INSERT INTO probe (n) VALUES (1)"))
        time.sleep(0.02)  # hold the write lock a little, as real bookings do
        return Out(n=1)

    def read(db: DB) -> Out:
        return Out(n=db.execute(text("SELECT COUNT(*) FROM probe")).scalar_one())

    app.add_api_route("/probe/write", write, methods=["POST"], response_model=Out)
    app.add_api_route("/probe/read", read, methods=["GET"], response_model=Out)
    commit_in_handler(app)
    return app


def test_writes_and_reads_do_not_stall_when_worker_threads_run_out(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path / 'lock.db'}", rate_limit_enabled=False)
    writer = database.build_engine(settings)
    reader = database.build_engine(settings, sqlite_begin="DEFERRED")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, n INTEGER)"))
    monkeypatch.setattr(database, "engine", writer)
    monkeypatch.setattr(database, "read_engine", reader)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=writer, expire_on_commit=False, class_=Session))
    monkeypatch.setattr(database, "ReadSessionLocal", sessionmaker(bind=reader, expire_on_commit=False, class_=Session, info={"read_only": True}))
    app = _app()

    async def main() -> tuple[list[int], float]:
        anyio.to_thread.current_default_thread_limiter().total_tokens = 3
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
            started = time.perf_counter()
            calls = [client.post("/probe/write") for _ in range(24)] + [client.get("/probe/read") for _ in range(12)]
            responses = await asyncio.gather(*calls)
            return [r.status_code for r in responses], time.perf_counter() - started

    statuses, seconds = asyncio.run(main())
    assert statuses == [200] * 36
    assert seconds < 10, f"requests stalled for {seconds:.1f}s"
    with writer.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM probe")).scalar_one() == 24
    writer.dispose()
    reader.dispose()
