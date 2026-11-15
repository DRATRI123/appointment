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
from starlette.requests import Request

from app.core.config import Settings, get_settings

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def build_engine(settings: Settings | None = None, *, sqlite_begin: str = "IMMEDIATE") -> Engine:
    """``sqlite_begin`` picks how SQLite transactions start: IMMEDIATE takes the single write lock up front (writers),
    DEFERRED takes no lock and, with WAL, reads in parallel with the writer (read-only requests)."""
    settings = settings or get_settings()
    url = settings.database_url
    kwargs: dict = {"echo": settings.database_echo, "future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" not in url and url not in ("sqlite://", "sqlite:///"):
            # Enough connections for every worker thread (40), so a request never waits for one while holding another.
            kwargs["pool_size"] = settings.database_pool_size
            kwargs["max_overflow"] = max(settings.database_max_overflow, 40 - settings.database_pool_size)
            kwargs["pool_timeout"] = settings.database_pool_timeout_seconds
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
        _configure_sqlite(engine, sqlite_begin)
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


def _configure_sqlite(engine: Engine, begin: str = "IMMEDIATE") -> None:
    statement = {"IMMEDIATE": "BEGIN IMMEDIATE", "DEFERRED": "BEGIN DEFERRED"}[begin]

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
    def _begin(conn) -> None:  # pragma: no cover - driver hook
        # Writers: serialise up-front so slot reservation cannot race on SQLite. Readers: no lock at all (WAL).
        conn.exec_driver_sql(statement)


engine: Engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
# Read-only requests. On SQLite they must not queue behind the single write lock: under load every worker thread
# ended up waiting for it while the request holding it waited for a free thread to send its response (measured: all
# requests stalled 30 s at 100 users). On PostgreSQL there is no difference, so both use the same engine.
read_engine: Engine = build_engine(sqlite_begin="DEFERRED") if engine.dialect.name == "sqlite" else engine
ReadSessionLocal = sessionmaker(bind=read_engine, autoflush=False, expire_on_commit=False, class_=Session, info={"read_only": True})


@event.listens_for(ReadSessionLocal, "before_flush")
def _warn_write_in_read_request(session: Session, _ctx, _instances) -> None:  # pragma: no cover - exercised by load tests
    """A write inside a GET still works on SQLite unless another write committed meanwhile, then it fails with
    "database is locked". Endpoints that write while answering a GET are marked with ``writes_on_read``; this warning
    catches any that are not."""
    changed = list(session.new) + list(session.deleted) + [o for o in session.dirty if session.is_modified(o)]
    if changed:
        from app.core.logging import get_logger

        get_logger("db").warning("db.write_in_read_request", path=session.info.get("path"), objects=sorted({type(o).__name__ for o in changed}))


def writes_on_read(endpoint):
    """Mark a GET endpoint that writes (an access audit, a usage counter): it gets a write session."""
    endpoint.db_writes = True
    return endpoint


def _api_key_request(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    return bool(request.headers.get("x-api-key")) or auth[7:].startswith("ak_live_")


def _wants_write_session(request: Request) -> bool:
    if request.method not in READ_METHODS:
        return True
    if getattr(request.scope.get("endpoint"), "db_writes", False):
        return True
    return _api_key_request(request)  # API-key calls record usage on every request, so they always write


def begin_writing(db: Session) -> None:
    """Switch a write request's session from reading to writing, at the start of the endpoint (its own thread).

    Ends the read-only transaction its dependencies used, so the endpoint's first statement starts a fresh one that
    takes the write lock (BEGIN IMMEDIATE on SQLite). Objects already loaded stay usable."""
    if db.get_bind() is engine:
        return
    if db.in_transaction():
        if db.new or db.dirty or db.deleted:  # a dependency changed something: keep its transaction as it is
            from app.core.logging import get_logger

            get_logger("db").warning("db.write_in_dependency", path=db.info.get("path"))
            return
        db.commit()
    db.bind = engine


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, committed on success, rolled back on error.

    FastAPI runs every sync dependency and the endpoint in separate worker threads. On SQLite a request must therefore
    never hold the single write lock while waiting for the next thread, or under load all threads end up waiting for
    a lock whose holder waits for a thread. So:
    * read-only requests never take it (WAL lets them read in parallel);
    * write requests read without it while their dependencies run (who is signed in, which clinic), and take it when
      the endpoint itself starts, in the endpoint's thread, which also commits before returning (``commit_in_handler``
      in app.main). API-key requests record usage in their dependencies, so they take it from the start.
    On PostgreSQL there is no single write lock and all of this changes nothing."""
    if not _wants_write_session(request):
        db = ReadSessionLocal()
    elif _api_key_request(request):
        db = SessionLocal()
    else:
        db = SessionLocal(bind=read_engine)
        db.info["write_lock_in_handler"] = True
    db.info["commit_in_handler"] = True
    db.info["path"] = request.url.path
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
