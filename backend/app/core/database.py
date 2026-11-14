"""Database engine and session management.

SQLite is used for development; PostgreSQL in production. All dialect-specific tuning lives here so
business logic stays database independent.
"""
from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    url = settings.database_url
    kwargs: dict = {"echo": settings.database_echo, "future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
        kwargs["pool_timeout"] = settings.database_pool_timeout_seconds
        kwargs["pool_recycle"] = 1800  # drop connections older than 30 minutes (load balancers and proxies cut idle ones)
        if url.startswith("postgresql") and settings.database_statement_timeout_ms:
            kwargs["connect_args"] = {"options": f"-c statement_timeout={int(settings.database_statement_timeout_ms)}",
                                      "application_name": "appointment-platform"}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    if settings.database_slow_query_ms:
        _log_slow_queries(engine, settings.database_slow_query_ms)
    return engine


def _log_slow_queries(engine: Engine, threshold_ms: int) -> None:
    """Warn about slow statements with their SQL text and duration. Parameters are never logged: they hold names,
    mobile numbers and UTRs."""
    import time

    from app.core.logging import get_logger

    log = get_logger("db.slow")

    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - driver hook
        conn.info.setdefault("query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _end(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - driver hook
        started = conn.info["query_start"].pop()
        ms = (time.perf_counter() - started) * 1000
        if ms >= threshold_ms:
            log.warning("db.slow_query", duration_ms=round(ms, 1), statement=" ".join(statement.split())[:500])


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - driver hook
        # Let SQLAlchemy control transactions so BEGIN IMMEDIATE below is the only BEGIN issued.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn) -> None:  # pragma: no cover - driver hook
        # Serialise writers up-front so slot reservation cannot race on SQLite.
        conn.exec_driver_sql("BEGIN IMMEDIATE")


engine: Engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, committed on success, rolled back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        if getattr(exc, "persist_changes", False):
            db.commit()  # e.g. a failed-login counter: the error is the answer, the counter must still be saved
        else:
            db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts and workers."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        if getattr(exc, "persist_changes", False):
            db.commit()  # e.g. a failed-login counter: the error is the answer, the counter must still be saved
        else:
            db.rollback()
        raise
    finally:
        db.close()


def lock_row(db: Session, obj):
    """Lock ``obj``'s row until the transaction ends and reload its committed values.

    Call it first in any method that reads a status and then acts on it (verify a payment, request a refund, cancel an
    appointment). On PostgreSQL concurrent requests otherwise all see the old status and all proceed: a payment
    verified twice, refunds beyond what was paid. The second request now waits, then sees the new status and is
    refused. On SQLite the whole database is already locked for the transaction, so this costs nothing there.
    Pending changes are flushed first, so nothing made earlier in this transaction is lost by the reload."""
    db.flush()
    model = type(obj)
    # The row must actually be fetched: the ORM refreshes the object only as rows are loaded.
    locked = db.scalars(select(model).where(model.id == obj.id).with_for_update().execution_options(populate_existing=True)).one()
    return locked
