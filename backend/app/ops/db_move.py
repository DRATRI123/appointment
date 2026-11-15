"""Database tasks the platform super admin can run from the browser (Super admin → Database), without commands.

* Apply database updates (``alembic upgrade head``).
* Move from SQLite to PostgreSQL:
    1. pause saving (patients and staff see "back in a few minutes"; nothing new is written that would be lost),
    2. apply any pending updates to the SQLite database,
    3. take a consistent snapshot of it (kept as a backup next to the original),
    4. copy it into the empty PostgreSQL database and check every table matches exactly (app.ops.migrate_data:
       one transaction, so a failure leaves PostgreSQL empty and nothing changes for the clinic),
    5. point DATABASE_URL in backend/.env at PostgreSQL (the old file is kept as .env.before-postgresql),
    6. ask for a restart. Saving stays paused until then, so nothing is written to the old SQLite by mistake.
  "Undo" before restarting puts the old .env back and resumes saving on SQLite.

Progress is kept in a small JSON file next to the database, so every API process (and a page reload) sees it.
The PostgreSQL password is only written into backend/.env (where it would be typed by hand otherwise); it is never
logged, returned by the API or kept in the progress file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config import BASE_DIR, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
ENV_FILE = BASE_DIR / ".env"
ENV_BACKUP = BASE_DIR / ".env.before-postgresql"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_HOST = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,253}$")
_job_lock = threading.Lock()
_pause_cache: tuple[float, float, bool] = (0.0, 0.0, False)  # (checked at, file mtime, paused)


class DatabaseTaskError(RuntimeError):
    """A problem to show to the super admin as it is."""


# ------------------------------------------------------------------------------------------------ files and state
def data_dir() -> Path:
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        return sqlite_path(url).parent
    return BASE_DIR / "data"


def sqlite_path(url: str) -> Path:
    raw = url.removeprefix("sqlite:///").split("?", 1)[0]
    path = Path(raw)
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def _status_file() -> Path:
    return data_dir() / "database-task.json"


def _pause_file() -> Path:
    return data_dir() / "saving-paused.json"


def _db_fingerprint(url: str | None = None) -> str:
    return hashlib.sha256((url or get_settings().database_url).encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_status() -> dict[str, Any] | None:
    try:
        status = json.loads(_status_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if status.get("state") == "running" and status.get("pid") != os.getpid() and not _pid_alive(status.get("pid")):
        status.update(state="failed", error="The app was stopped while this was running. Nothing was switched; you can start again.")
        _write_json(_status_file(), status)
        resume_saving()
    return status


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except SystemError:  # Windows raises this for some processes it cannot signal; treat as alive
        return True
    return True


def _update(**fields: Any) -> None:
    status = read_status() or {}
    status.update(fields)
    if "step" in fields:
        status.setdefault("log", []).append(f"{_now()}  {fields['step']}")
        status["log"] = status["log"][-60:]
    _write_json(_status_file(), status)


# ------------------------------------------------------------------------------------------------ pause saving
def pause_saving(reason: str) -> None:
    _write_json(_pause_file(), {"database": _db_fingerprint(), "reason": reason, "since": _now()})
    _reset_pause_cache()


def resume_saving() -> None:
    try:
        _pause_file().unlink()
    except FileNotFoundError:
        pass
    _reset_pause_cache()


def _reset_pause_cache() -> None:
    global _pause_cache
    _pause_cache = (0.0, 0.0, False)


def saving_paused() -> bool:
    """True while a database task needs the current database left untouched. Checked on every write request, so
    it only looks at the file at most once a second."""
    global _pause_cache
    now = time.monotonic()
    checked, mtime, paused = _pause_cache
    if now - checked < 1.0:
        return paused
    try:
        st = _pause_file().stat()
    except OSError:
        _pause_cache = (now, 0.0, False)
        return False
    if st.st_mtime == mtime:
        _pause_cache = (now, mtime, paused)
        return paused
    try:
        data = json.loads(_pause_file().read_text(encoding="utf-8"))
        paused = data.get("database") == _db_fingerprint()  # after the switch, the new database is not paused
    except (OSError, ValueError):
        paused = False
    _pause_cache = (now, st.st_mtime, paused)
    return paused


# ------------------------------------------------------------------------------------------------ overview
def _alembic_config(url: str):
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.attributes["database_url"] = url
    return cfg


def pending_updates(url: str | None = None) -> list[str]:
    from alembic.script import ScriptDirectory

    url = url or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            try:
                current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:  # noqa: BLE001 - a brand-new database has no version table yet
                current = None
    finally:
        engine.dispose()
    script = ScriptDirectory.from_config(_alembic_config(url))
    return [rev.doc or rev.revision for rev in script.iterate_revisions("heads", current or "base")][::-1]


def overview() -> dict[str, Any]:
    s = get_settings()
    url = make_url(s.database_url)
    info: dict[str, Any] = {"engine": "sqlite" if url.drivername.startswith("sqlite") else "postgresql" if url.drivername.startswith("postgresql") else url.drivername}
    if info["engine"] == "sqlite":
        path = sqlite_path(s.database_url)
        info["location"] = str(path)
        info["size_bytes"] = path.stat().st_size if path.exists() else 0
    else:
        info["location"] = f"{url.host or 'localhost'}:{url.port or 5432}/{url.database}"
    try:
        info["pending_updates"] = pending_updates()
    except Exception as exc:  # noqa: BLE001
        info["pending_updates"] = []
        info["error"] = f"Could not read the database version: {type(exc).__name__}"
    info["saving_paused"] = saving_paused()
    info["can_switch_automatically"] = "DATABASE_URL" not in os.environ  # set outside .env (Docker, a service): change it there
    info["env_backup_exists"] = ENV_BACKUP.exists()
    info["task"] = read_status()
    return info


# ------------------------------------------------------------------------------------------------ PostgreSQL target
@dataclass
class Target:
    host: str
    port: int
    database: str
    user: str
    password: str

    def validate(self) -> None:
        if not _HOST.match(self.host or ""):
            raise DatabaseTaskError("Enter the PostgreSQL server name or address, e.g. localhost.")
        if not 1 <= int(self.port) <= 65535:
            raise DatabaseTaskError("The port must be a number from 1 to 65535 (usually 5432).")
        if not _NAME.match(self.database or ""):
            raise DatabaseTaskError("The database name may only use letters, numbers and _ (e.g. appointments).")
        if not self.user or len(self.user) > 63:
            raise DatabaseTaskError("Enter the PostgreSQL user name.")

    def url(self, database: str | None = None) -> URL:
        return URL.create("postgresql+psycopg", username=self.user, password=self.password or None, host=self.host,
                          port=int(self.port), database=database or self.database)

    def label(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.database}"


def _engine(url: URL):
    return create_engine(url, connect_args={"connect_timeout": 8}, pool_pre_ping=True)


def _plain_error(exc: Exception) -> str:
    msg = str(getattr(exc, "orig", None) or exc).strip().splitlines()[0][:300]
    lowered = msg.lower()
    if "password authentication failed" in lowered:
        return "PostgreSQL said the user name or password is wrong."
    if "does not exist" in lowered and "database" in lowered:
        return "That database does not exist yet. Use “Create the database”."
    if "connection refused" in lowered or "could not connect" in lowered or "timeout" in lowered or "name or service not known" in lowered:
        return "Could not reach PostgreSQL at that address. Is PostgreSQL installed and running, and are the server and port right?"
    return msg


def test_target(t: Target) -> dict[str, Any]:
    t.validate()
    engine = _engine(t.url())
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar()
            tables = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")).scalar()
            has_data = False
            if tables:
                from app.ops.migrate_data import _target_has_data

                has_data = bool(_target_has_data(conn))
    except Exception as exc:  # noqa: BLE001
        message = _plain_error(exc)
        return {"ok": False, "exists": "does not exist" not in message, "message": message}
    finally:
        engine.dispose()
    major = int(str(version).split(".")[0]) if str(version).split(".")[0].isdigit() else 0
    if has_data:
        return {"ok": False, "exists": True, "version": version, "message": "This database already has data. Use a new, empty database."}
    if major and major < 13:
        return {"ok": False, "exists": True, "version": version, "message": f"PostgreSQL {version} is too old. Use version 13 or newer (16 recommended)."}
    return {"ok": True, "exists": True, "version": version, "message": f"Connected to PostgreSQL {version}. The database is empty and ready."}


def create_target_database(t: Target) -> dict[str, Any]:
    t.validate()
    engine = create_engine(t.url("postgres"), connect_args={"connect_timeout": 8}, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": t.database}).scalar()
            if not exists:
                # CREATE DATABASE cannot take a bound parameter; the name was checked against _NAME (letters, digits, _).
                conn.execute(text(f'CREATE DATABASE "{t.database}"'))  # nosemgrep: sql-built-with-string-formatting
    except Exception as exc:  # noqa: BLE001
        msg = _plain_error(exc)
        if "permission denied" in msg.lower():
            msg = "This PostgreSQL user may not create databases. Create it in pgAdmin (or ask your provider), then test again."
        raise DatabaseTaskError(msg) from exc
    finally:
        engine.dispose()
    return test_target(t)


# ------------------------------------------------------------------------------------------------ background tasks
def _start(kind: str, worker, *args, **extra: Any) -> None:
    status = read_status()
    if status and status.get("state") == "running":
        raise DatabaseTaskError("Another database task is still running. Wait for it to finish.")
    if not _job_lock.acquire(blocking=False):
        raise DatabaseTaskError("Another database task is still running. Wait for it to finish.")
    _write_json(_status_file(), {"kind": kind, "state": "running", "pid": os.getpid(), "started_at": _now(), "log": [], **extra})

    def run() -> None:
        try:
            worker(*args)
        except Exception as exc:  # noqa: BLE001 - shown on the page
            log.exception("database_task.failed", kind=kind)
            _update(state="failed", finished_at=_now(),
                    error=str(exc) if isinstance(exc, DatabaseTaskError) else f"{type(exc).__name__}: {str(exc)[:300]}")
            if not (read_status() or {}).get("switched"):
                resume_saving()
        finally:
            _job_lock.release()

    threading.Thread(target=run, name=f"database-{kind}", daemon=True).start()


def start_updates() -> None:
    _start("updates", _run_updates)


def _run_updates() -> None:
    from alembic import command

    pending = pending_updates()
    if not pending:
        _update(step="Already up to date. Nothing to do.", state="done", finished_at=_now())
        return
    _update(step="Pausing saving for a moment")
    pause_saving("Applying database updates")
    time.sleep(2)  # let requests that are already saving finish
    for name in pending:
        _update(step=f"Update: {name}")
    command.upgrade(_alembic_config(get_settings().database_url), "head")
    resume_saving()
    _update(step="All updates applied. Saving has resumed.", state="done", finished_at=_now())


def start_move(t: Target) -> None:
    t.validate()
    if not get_settings().database_url.startswith("sqlite"):
        raise DatabaseTaskError("The app already uses PostgreSQL.")
    check = test_target(t)
    if not check["ok"]:
        raise DatabaseTaskError(check["message"])
    _start("move", _run_move, t, target=t.label())


def _run_move(t: Target) -> None:
    from alembic import command

    from app.ops.migrate_data import migrate, prepare_sqlite, sqlite_source_url

    s = get_settings()
    source = sqlite_path(s.database_url)
    _update(step="Pausing saving (patients and staff see “back in a few minutes”)")
    pause_saving("Moving to PostgreSQL")
    time.sleep(3)  # let requests that are already saving finish
    if pending_updates():
        _update(step="Applying waiting database updates first")
        command.upgrade(_alembic_config(s.database_url), "head")
    snapshot = source.with_name(f"{source.stem}-before-postgresql-{datetime.now(UTC):%Y%m%d-%H%M%S}.db")
    _update(step=f"Taking a snapshot of the current database (kept as {snapshot.name})")
    live, copy = sqlite3.connect(source), sqlite3.connect(snapshot)
    try:
        live.backup(copy)
    finally:
        copy.close()
        live.close()
    prepare_sqlite(snapshot)
    src_engine, dst_engine = create_engine(sqlite_source_url(snapshot)), _engine(t.url())
    try:
        report = migrate(src_engine, dst_engine, progress=lambda msg: _update(step=msg))
    finally:
        src_engine.dispose()
        dst_engine.dispose()
    _update(step=f"Copied and checked {report.total_rows:,} rows in {sum(1 for v in report.tables.values() if v)} tables",
            rows=report.total_rows, snapshot=str(snapshot))
    if "DATABASE_URL" in os.environ:
        _update(state="done", finished_at=_now(), switched=False,
                step="Copy finished. DATABASE_URL is set outside backend/.env on this server: change it there to the "
                     f"new PostgreSQL database ({t.label()}), then restart. Saving stays paused until then.")
        return
    _switch_env(t.url().render_as_string(hide_password=False))
    _update(state="done", finished_at=_now(), switched=True,
            step="Switched backend/.env to PostgreSQL. Restart the app now (close its windows and double-click "
                 "START-APP.bat). Saving stays paused until the restart.")


def _switch_env(url: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    if ENV_FILE.exists() and not ENV_BACKUP.exists():
        ENV_BACKUP.write_text("\n".join(lines) + "\n", encoding="utf-8")
    new = f"DATABASE_URL={url}"
    out, replaced = [], False
    for line in lines:
        if re.match(r"^\s*DATABASE_URL\s*=", line):
            out.append(new if not replaced else f"# {line}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(new)
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_FILE)


def undo_switch() -> None:
    """Before restarting: go back to SQLite (restore the old .env) and resume saving."""
    status = read_status() or {}
    if status.get("state") == "running":
        raise DatabaseTaskError("Wait for the running task to finish first.")
    if ENV_BACKUP.exists():
        os.replace(ENV_BACKUP, ENV_FILE)
    resume_saving()
    _update(state="undone", step="Undone: the app keeps using SQLite and saving has resumed.", switched=False, finished_at=_now())
