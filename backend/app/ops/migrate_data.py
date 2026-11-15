"""Move all data from SQLite (development / single PC) to PostgreSQL (production).

    python -m app.ops.migrate_data --source sqlite:///data/app.db \\
        --target postgresql+psycopg://app:PASSWORD@HOST:5432/appointments [--dry-run]

What it does, in order:
1. Checks the source is at the schema version this release expects (run `alembic upgrade head` on it first).
2. Creates the schema on the target with the real migrations, and refuses to continue if the target already holds
   any business data (it never merges into or overwrites a live database). Seed rows that a fresh server creates on
   first start (roles, permissions, platform settings) are replaced by the source's copies.
3. Copies every table in dependency order, keeping every ID, so links, references and audit history stay intact.
   Dates, money (integer paise), JSON and encrypted fields are copied as values, not re-encoded, so encrypted notes
   still open with the same DATA_ENCRYPTION_KEY.
4. Moves PostgreSQL's ID counters past the copied rows so new records do not collide.
5. Proves the copy: the row count and a SHA-256 checksum of every table must match the source exactly.

The copy runs in a single transaction: any failure, including a failed check in step 5, leaves the target empty.
Uploaded files are not in the database; copy the uploads folder (or volume) separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Table, create_engine, func, select, text
from sqlalchemy.engine import Connection

from app.models import Base

BATCH = 1000
# Written by the seed step (roles, permissions, platform settings), which a fresh server runs on its first start.
# They are not business data: the source's own copies replace them, so IDs referenced by memberships still match.
SEED_TABLES = ("permissions", "system_settings", "roles", "role_permissions")


class MigrationError(RuntimeError):
    pass


@dataclass
class Report:
    tables: dict[str, int] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)
    sequences_reset: int = 0
    dry_run: bool = False

    @property
    def total_rows(self) -> int:
        return sum(self.tables.values())


def _tables() -> list[Table]:
    return list(Base.metadata.sorted_tables)  # parents before children (no foreign-key cycles in this schema)


def _revision(conn: Connection) -> str | None:
    names = set(conn.dialect.get_table_names(conn))
    if "alembic_version" not in names:
        return None  # a brand-new, empty database
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def prepare_sqlite(path: Path) -> None:
    """Make an SQLite database a single, complete, portable file.

    The app runs SQLite in WAL mode: recent changes can live in a side file (app.db-wal) until a checkpoint. Copying
    only app.db would lose them. This folds the log into the main file and switches to rollback-journal mode, so the
    one file holds everything. Run it on the PC after stopping the API and worker."""
    if not path.exists():
        raise MigrationError(f"{path} does not exist.")
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        mode = con.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    if mode.lower() != "delete":
        raise MigrationError("The database is still in use (could not leave WAL mode). Stop the API and worker first.")
    if ok != "ok":
        raise MigrationError(f"SQLite integrity check failed: {ok}")


def sqlite_source_url(path: Path) -> str:
    """Open the source read-only, without creating lock or WAL files (works from a read-only mount)."""
    wal = Path(f"{path}-wal")
    if wal.exists() and wal.stat().st_size > 0:
        raise MigrationError(f"{wal.name} still holds recent changes that are not in {path.name}. "
                             "Run `python -m app.ops.migrate_data --prepare-sqlite <file>` on the PC first.")
    return f"sqlite:///file:{path.resolve().as_posix()}?mode=ro&immutable=1&uri=true"


def _norm(value: Any) -> Any:
    """A representation that is identical whichever database the value was read from."""
    if isinstance(value, datetime):  # the same instant may come back with a different offset per database
        return (value.astimezone(UTC) if value.tzinfo else value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return repr(value)
    return value


def table_checksum(conn: Connection, table: Table) -> tuple[int, str]:
    """Row count and SHA-256 over every row (ordered by primary key), read through the model's column types."""
    h = hashlib.sha256()
    order = list(table.primary_key.columns) or list(table.columns)
    rows = 0
    for row in conn.execute(select(table).order_by(*order)).yield_per(BATCH):
        h.update(json.dumps([_norm(v) for v in row], sort_keys=True, default=str).encode())
        rows += 1
    return rows, h.hexdigest()


def _target_has_data(conn: Connection) -> list[str]:
    """Tables holding business data. Seed-only rows (roles, permissions, platform settings) do not count."""
    busy = []
    for table in _tables():
        if table.name in SEED_TABLES:
            continue
        if conn.execute(select(func.count()).select_from(table)).scalar():
            busy.append(table.name)
    return busy


def _migrate_schema(target_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import BASE_DIR

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.attributes["database_url"] = target_url
    command.upgrade(cfg, "head")


def _reset_sequences(conn: Connection) -> int:
    n = 0
    for table in _tables():
        pk = list(table.primary_key.columns)
        if len(pk) != 1 or not pk[0].autoincrement or pk[0].type.python_type is not int:
            continue
        seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": table.name, "c": pk[0].name}).scalar()
        if seq:
            # Next id = max(id) + 1, or 1 for an empty table.
            top = conn.execute(select(func.max(pk[0]))).scalar()
            conn.execute(text("SELECT setval(:s, :v, :called)"), {"s": seq, "v": top or 1, "called": top is not None})
            n += 1
    return n


def migrate(source: Engine, target: Engine, *, dry_run: bool = False, migrate_target_schema: bool = True,
            progress: Callable[[str], None] | None = None) -> Report:
    """``progress`` (optional) receives short plain-language updates, e.g. for the Super admin Database page."""
    from app.core.observability import migration_head

    say = progress or (lambda _msg: None)

    head = migration_head()
    report = Report(dry_run=dry_run)
    if target.dialect.name != "postgresql":
        raise MigrationError("The target must be a PostgreSQL database (postgresql+psycopg://...).")

    say("Reading the current database")
    with source.connect() as src:
        rev = _revision(src)
        if rev != head:
            raise MigrationError(f"The source database is at schema {rev}; this release needs {head}. "
                                 "Run `alembic upgrade head` against the source first (back it up before).")
        source_sums = {}
        for table in _tables():
            source_sums[table.name] = table_checksum(src, table)
            report.tables[table.name] = source_sums[table.name][0]

    if dry_run:
        with target.connect() as tgt:
            if _revision(tgt) is not None and (busy := _target_has_data(tgt)):
                raise MigrationError(f"The target already contains data ({', '.join(busy[:5])}...). Use an empty database.")
        report.checksums = {name: s for name, (_, s) in source_sums.items()}
        return report

    if migrate_target_schema:
        say("Creating the tables in PostgreSQL")
        _migrate_schema(target.url.render_as_string(hide_password=False))
    with target.connect() as tgt:
        if _revision(tgt) != head:
            raise MigrationError(f"The target schema is at {_revision(tgt)}, expected {head}.")
        if busy := _target_has_data(tgt):
            raise MigrationError(f"The target already contains data ({', '.join(busy[:5])}...). "
                                 "This tool only fills an empty database; it never merges or overwrites.")

    with source.connect() as src, target.begin() as tgt:  # one transaction: all or nothing
        for table in reversed([t for t in _tables() if t.name in SEED_TABLES]):  # children first
            tgt.execute(table.delete())
        for table in _tables():
            if report.tables.get(table.name):
                say(f"Copying {table.name} ({report.tables[table.name]:,} rows)")
            batch: list[dict[str, Any]] = []
            for row in src.execute(select(table)).mappings().yield_per(BATCH):
                batch.append(dict(row))
                if len(batch) >= BATCH:
                    tgt.execute(table.insert(), batch)
                    batch = []
            if batch:
                tgt.execute(table.insert(), batch)
        report.sequences_reset = _reset_sequences(tgt)
        say("Checking every table matches the original exactly")
        for table in _tables():
            copied = table_checksum(tgt, table)
            if copied != source_sums[table.name]:
                raise MigrationError(f"Verification failed for {table.name}: source {source_sums[table.name][0]} rows, "
                                     f"target {copied[0]} rows, or the contents differ. Nothing was saved.")
            report.checksums[table.name] = copied[1]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ops.migrate_data", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prepare-sqlite", type=Path, metavar="FILE", help="on the PC: make FILE complete and portable, then exit")
    parser.add_argument("--source", help="sqlite:///path/to/app.db (or any SQLAlchemy URL)")
    parser.add_argument("--target", help="postgresql+psycopg://user:password@host:5432/dbname (empty)")
    parser.add_argument("--dry-run", action="store_true", help="check everything and count rows, write nothing")
    args = parser.parse_args(argv)
    if args.prepare_sqlite:
        try:
            prepare_sqlite(args.prepare_sqlite)
        except MigrationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.prepare_sqlite} is complete and ready to copy ({args.prepare_sqlite.stat().st_size:,} bytes).")
        return 0
    if not (args.source and args.target):
        parser.error("--source and --target are required (or use --prepare-sqlite FILE)")
    try:
        source_url = args.source
        if source_url.startswith("sqlite:///") and "uri=true" not in source_url:
            source_url = sqlite_source_url(Path(source_url.removeprefix("sqlite:///")))
        source, target = create_engine(source_url), create_engine(args.target)
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        report = migrate(source, target, dry_run=args.dry_run)
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        source.dispose()
        target.dispose()
    non_empty = {k: v for k, v in report.tables.items() if v}
    width = max((len(k) for k in non_empty), default=10)
    for name, rows in sorted(non_empty.items()):
        print(f"  {name:<{width}}  {rows:>8,}")
    if report.dry_run:
        print(f"Dry run: {report.total_rows:,} rows in {len(non_empty)} tables would be copied. Nothing was written.")
    else:
        print(f"Copied and verified {report.total_rows:,} rows in {len(non_empty)} tables (row counts and SHA-256 checksums "
              f"match); {report.sequences_reset} ID counters moved past the copied rows.")
        print("Next: copy the uploads folder, point DATABASE_URL at PostgreSQL, start the API and check System health.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
