"""Shared fixtures: an isolated SQLite database per test session, app and client."""
from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("PUBLIC_CACHE_SECONDS", "0")
os.environ.setdefault("PLATFORM_ADMIN_REQUIRE_MFA", "false")  # most tests make quick super admins; test_superadmin.py turns it on  # tests share one uncommitted session; test_public_cache.py covers the cache

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.seed import seed_all  # noqa: E402


@pytest.fixture(scope="session")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("db") / "test.db"


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")  # e.g. postgresql+psycopg://app:pw@127.0.0.1/app_test


def is_postgres() -> bool:
    return bool(TEST_DATABASE_URL and TEST_DATABASE_URL.startswith("postgresql"))


@pytest.fixture(scope="session")
def engine(db_path: Path):
    """SQLite file by default; the whole suite runs on PostgreSQL when TEST_DATABASE_URL is set (CI does both)."""
    if is_postgres():
        eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        Base.metadata.drop_all(eng)
        with eng.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    else:
        eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    # Equivalent of `alembic stamp head`: the schema above is the current release (test_seed_and_migrations checks the
    # real migrations separately), so the readiness probe's migration check sees an up-to-date database.
    from sqlalchemy import text

    from app.core.observability import migration_head

    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": migration_head()})
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    seed_all(session)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def _override() -> Generator[Session, None, None]:
        """Mirror production get_db: each request runs in a SAVEPOINT that is rolled back on error (unless the error
        asks for its changes to persist), so tests see exactly what a real request would have saved."""
        for key in ("branch_scope", "mask_contacts", "privacy_policy"):  # in production every request has its own session; here they share one
            db.info.pop(key, None)
        savepoint = db.begin_nested()
        try:
            yield db
        except Exception as exc:
            if savepoint.is_active:
                if getattr(exc, "persist_changes", False):
                    savepoint.commit()
                else:
                    savepoint.rollback()
            raise
        else:
            if savepoint.is_active:
                savepoint.commit()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
