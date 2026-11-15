"""Super admin → Database: updates and the move to PostgreSQL, run from the browser (no commands)."""
from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Organization, User
from app.ops import db_move
from tests.conftest import TEST_DATABASE_URL, is_postgres
from tests.helpers import PASSWORD, bearer, create_org, register


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """The page works on the app's configured database and backend/.env: point both at a temporary copy."""
    from alembic import command

    url = f"sqlite:///{tmp_path / 'app.db'}"
    command.upgrade(db_move._alembic_config(url), "head")
    monkeypatch.setattr(get_settings(), "database_url", url)
    monkeypatch.setattr(db_move, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(db_move, "ENV_BACKUP", tmp_path / ".env.before-postgresql")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(f"APP_ENV=development\nDATABASE_URL={url}\nRATE_LIMIT_ENABLED=true\n")
    db_move._reset_pause_cache()
    yield tmp_path
    db_move.resume_saving()


def _admin(client, db, email="root-db@example.com"):
    h = bearer(register(client, email, "Platform Root"))
    db.scalar(select(User).where(User.email == email)).is_platform_admin = True
    db.flush()
    return h


def _wait(client, h, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        task = client.get("/api/v1/platform/database", headers=h).json()["task"]
        if task and task["state"] != "running":
            return task
        time.sleep(0.3)
    raise AssertionError("database task did not finish")


def test_only_the_platform_admin_can_see_it(client, sandbox):
    h = bearer(register(client, "not-root@example.com"))
    assert client.get("/api/v1/platform/database", headers=h).status_code == 403


def test_overview_shows_sqlite_and_no_waiting_updates(client, db, sandbox):
    info = client.get("/api/v1/platform/database", headers=_admin(client, db)).json()
    assert info["engine"] == "sqlite" and info["pending_updates"] == [] and info["saving_paused"] is False
    assert info["can_switch_automatically"] is True


def test_paused_saving_refuses_writes_but_not_reading_or_sign_in(client, db, sandbox):
    h = _admin(client, db)
    org = create_org(client, h, "Pause Clinic")
    th = {**h, "X-Organization-Id": org["id"]}
    db_move.pause_saving("test")
    r = client.post("/api/v1/branches", json={"name": "Main", "code": "MAIN"}, headers=th)
    assert r.status_code == 503 and r.json()["code"] == "maintenance"
    assert client.get("/api/v1/branches", headers=th).status_code == 200
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": "root-db@example.com", "password": PASSWORD}).status_code == 200
    db_move.resume_saving()
    assert client.post("/api/v1/branches", json={"name": "Main", "code": "MAIN"}, headers=th).status_code == 201


def test_actions_need_your_password(client, db, sandbox):
    h = _admin(client, db)
    r = client.post("/api/v1/platform/database/updates", json={"confirm_password": "wrong-password1"}, headers=h)
    assert r.status_code == 401
    r = client.post("/api/v1/platform/database/updates", json={"confirm_password": PASSWORD}, headers=h)
    assert r.status_code == 200
    assert _wait(client, h)["state"] == "done"


def test_bad_postgresql_details_are_explained(client, db, sandbox):
    h = _admin(client, db)
    r = client.post("/api/v1/platform/database/test", json={"host": "127.0.0.1", "port": 1, "database": "x", "user": "u", "password": "p"}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is False and "reach PostgreSQL" in r.json()["message"]
    r = client.post("/api/v1/platform/database/test", json={"host": "localhost", "database": "bad name;", "user": "u"}, headers=h)
    assert r.status_code == 422


@pytest.mark.skipif(not is_postgres(), reason="needs TEST_DATABASE_URL pointing at PostgreSQL")
def test_move_to_postgresql_from_the_page(client, db, sandbox):
    base = make_url(TEST_DATABASE_URL)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "app_test_dbmove" WITH (FORCE)'))
    admin.dispose()
    # Something to copy: a clinic in the (temporary) SQLite database.
    src = create_engine(get_settings().database_url)
    with Session(src) as s:
        s.add(Organization(slug="moved-clinic", code="MOVED", name="Moved Clinic"))
        s.commit()
    src.dispose()

    h = _admin(client, db)
    target = {"host": base.host, "port": base.port or 5432, "database": "app_test_dbmove", "user": base.username, "password": base.password}
    first = client.post("/api/v1/platform/database/test", json=target, headers=h).json()
    assert first["ok"] is False and "does not exist" in first["message"]
    created = client.post("/api/v1/platform/database/create", json=target, headers=h)
    assert created.status_code == 200 and created.json()["ok"] is True, created.text

    r = client.post("/api/v1/platform/database/move", headers=h,
                    json={"target": target, "confirm_password": PASSWORD, "i_understand": True})
    assert r.status_code == 200, r.text
    task = _wait(client, h, 120)
    assert task["state"] == "done", task
    assert task["switched"] is True and task["rows"] >= 1
    assert any("Checking every table" in line for line in task["log"])
    env = (sandbox / ".env").read_text()
    assert "DATABASE_URL=postgresql+psycopg://" in env and "app_test_dbmove" in env and "RATE_LIMIT_ENABLED=true" in env
    assert (sandbox / ".env.before-postgresql").exists()
    assert client.get("/api/v1/platform/database", headers=h).json()["saving_paused"] is True  # until the restart

    pg = create_engine(base.set(database="app_test_dbmove"))
    with pg.connect() as conn:
        assert conn.execute(text("SELECT name FROM organizations WHERE slug = 'moved-clinic'")).scalar() == "Moved Clinic"
    pg.dispose()

    # Changed your mind before restarting: back to SQLite, saving resumes.
    undone = client.post("/api/v1/platform/database/undo", json={"confirm_password": PASSWORD}, headers=h)
    assert undone.status_code == 200 and undone.json()["saving_paused"] is False
    assert "sqlite:///" in (sandbox / ".env").read_text()
