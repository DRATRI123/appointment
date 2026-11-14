"""SQLite -> PostgreSQL data migration, on data created through the real app (needs TEST_DATABASE_URL)."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import create_app
from app.models import Appointment, Organization
from app.ops import migrate_data as md
from app.ops.migrate_data import MigrationError, migrate
from app.services.seed import seed_all
from tests.booking_helpers import Clinic, ist
from tests.conftest import TEST_DATABASE_URL, is_postgres
from tests.helpers import PASSWORD

needs_postgres = pytest.mark.skipif(not is_postgres(), reason="set TEST_DATABASE_URL to a PostgreSQL database")


def _fresh_pg(suffix: str) -> str:
    url = make_url(TEST_DATABASE_URL)
    name = f"{url.database}_{suffix}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return url.set(database=name).render_as_string(hide_password=False)


def _app_on(url: str) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
            db.commit()
        except Exception as exc:
            db.commit() if getattr(exc, "persist_changes", False) else db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    client.__enter__()
    return client, factory


@pytest.fixture()
def sqlite_with_real_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'clinic.db'}"
    md._migrate_schema(url)  # the real migrations, like a long-running SQLite install
    client, factory = _app_on(url)
    with factory() as db:
        seed_all(db)
        db.commit()
    c = Clinic(client, email="migrate-owner@example.com", name="Sunrise Ayurveda", payment_mode="pay_at_clinic")
    appts = [c.staff_book(ist(c.monday, 9 + i), customer={"full_name": f"Patient {i}", "mobile": f"98100000{i:02d}"}) for i in range(3)]
    customer_id = c.get("/customers")["data"][0]["id"]
    c.post(f"/customers/{customer_id}/notes", {"body": "Vata imbalance; avoid cold foods", "note_type": "general"})
    client.post(f"/api/v1/appointments/{appts[0]['id']}/status", json={"action": "cancel", "reason": "Fever"}, headers=c.h)
    client.__exit__(None, None, None)
    return url, c, customer_id


@needs_postgres
def test_full_migration_keeps_everything_working(sqlite_with_real_data):
    source_url, c, customer_id = sqlite_with_real_data
    target_url = _fresh_pg("migrate")
    source, target = create_engine(source_url), create_engine(target_url)

    dry = migrate(source, target, dry_run=True)
    assert dry.dry_run and dry.tables["appointments"] == 3
    with target.connect() as conn:  # a dry run writes nothing (the schema is not even created)
        assert conn.execute(text("SELECT to_regclass('public.appointments')")).scalar() is None

    report = migrate(source, target)
    assert report.tables["appointments"] == 3 and report.tables["customer_notes"] == 1 and report.sequences_reset > 30
    assert report.checksums == dry.checksums  # the copy is byte-for-byte the same data
    source.dispose()
    target.dispose()

    # The clinic carries on, on PostgreSQL: same login, same encrypted note, new bookings get fresh ids.
    client, factory = _app_on(target_url)
    r = client.post("/api/v1/auth/login", json={"email": "migrate-owner@example.com", "password": PASSWORD})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}", "X-Organization-Id": c.org["id"]}
    notes = client.get(f"/api/v1/customers/{customer_id}/notes", headers=h, params={"purpose": "migration check"})
    assert notes.status_code == 200 and notes.json()[0]["body"] == "Vata imbalance; avoid cold foods"
    statuses = sorted(a["status"] for a in client.get("/api/v1/appointments", headers=h).json())
    assert statuses == ["cancelled", "confirmed", "confirmed"]
    new = client.post("/api/v1/appointments", headers=h, json={
        "professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": ist(c.monday, 9).isoformat(),
        "customer": {"full_name": "After Move", "mobile": "9810000099"}, "source": "reception"})
    assert new.status_code == 201, new.text  # the cancelled 09:00 slot is free again; ids do not collide
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Appointment)) == 4
        assert db.scalar(select(Organization.name)) == "Sunrise Ayurveda"
    client.__exit__(None, None, None)


@needs_postgres
def test_refuses_a_target_that_already_has_data(sqlite_with_real_data):
    source_url, _, _ = sqlite_with_real_data
    target_url = _fresh_pg("busy")
    source, target = create_engine(source_url), create_engine(target_url)
    migrate(source, target)
    with pytest.raises(MigrationError, match="already contains data"):
        migrate(source, target)
    source.dispose()
    target.dispose()


@needs_postgres
def test_a_freshly_started_server_with_only_seed_data_is_accepted(sqlite_with_real_data):
    """The Docker stack migrates and seeds PostgreSQL on first start; importing afterwards must still work."""
    source_url, c, _ = sqlite_with_real_data
    target_url = _fresh_pg("seeded")
    md._migrate_schema(target_url)
    target = create_engine(target_url)
    with Session(target) as db:
        seed_all(db)
        db.commit()
    source = create_engine(source_url)
    report = migrate(source, target)
    assert report.tables["organizations"] == 1
    with target.connect() as conn:  # the source's roles replaced the seeded ones, so memberships still resolve
        assert conn.execute(text("SELECT COUNT(*) FROM organization_memberships m JOIN roles r ON r.id = m.role_id")).scalar() >= 1
    source.dispose()
    target.dispose()


@needs_postgres
def test_refuses_an_outdated_source(sqlite_with_real_data):
    source_url, _, _ = sqlite_with_real_data
    source = create_engine(source_url)
    with source.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'old0000'"))
    with pytest.raises(MigrationError, match="alembic upgrade head"):
        migrate(source, create_engine(_fresh_pg("old")))
    source.dispose()


@needs_postgres
def test_a_failed_verification_leaves_the_target_empty(sqlite_with_real_data, monkeypatch):
    source_url, _, _ = sqlite_with_real_data
    target_url = _fresh_pg("verify")
    source, target = create_engine(source_url), create_engine(target_url)
    real = md.table_checksum

    def corrupt(conn, table):
        rows, digest = real(conn, table)
        return (rows, "tampered") if conn.engine is target and table.name == "appointments" else (rows, digest)

    monkeypatch.setattr(md, "table_checksum", corrupt)
    with pytest.raises(MigrationError, match="Verification failed for appointments"):
        migrate(source, target)
    with target.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar() == 0  # rolled back: all or nothing
    source.dispose()
    target.dispose()


def test_prepare_sqlite_folds_pending_changes_into_the_file(tmp_path):
    """Recent writes in WAL mode live in app.db-wal; the source must be one complete file before it is copied."""
    import sqlite3

    db = tmp_path / "app.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")  # keep changes in the -wal file, like a busy clinic PC
    con.execute("CREATE TABLE t (x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    with pytest.raises(MigrationError, match="still holds recent changes"):
        md.sqlite_source_url(db)
    con.close()  # the API is stopped
    md.prepare_sqlite(db)
    assert not (tmp_path / "app.db-wal").exists() or (tmp_path / "app.db-wal").stat().st_size == 0
    ro = create_engine(md.sqlite_source_url(db))
    with ro.connect() as conn:
        assert conn.execute(text("SELECT x FROM t")).scalar() == 1  # the change made it into the single file
    ro.dispose()


def test_target_must_be_postgresql(tmp_path):
    with pytest.raises(MigrationError, match="PostgreSQL"):
        migrate(create_engine(f"sqlite:///{tmp_path / 'a.db'}"), create_engine(f"sqlite:///{tmp_path / 'b.db'}"))
