"""Database engine and session management.

SQLite is used for development; PostgreSQL in production. All dialect-specific tuning lives here so
business logic stays database independent.
"""
from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
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
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


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
