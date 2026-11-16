"""Backups: create, verify, restore, prune and list.

    python -m app.ops.backup create            # database + uploads -> BACKUP_DIR/backup-<UTC stamp>.tar.gz[.enc]
    python -m app.ops.backup verify <file>     # checksums, archive integrity, database readable
    python -m app.ops.backup restore <file> --yes
    python -m app.ops.backup prune             # apply BACKUP_KEEP_DAILY / _WEEKLY / _MONTHLY
    python -m app.ops.backup list

One backup is one file. Inside the archive:

    manifest.json           what, when, schema revision, row counts, SHA-256 of every file
    database.sqlite         SQLite online-backup copy (consistent while the app keeps running)   or
    database.dump           PostgreSQL custom-format dump (pg_dump -Fc; restore with pg_restore)
    uploads/...             the local upload folder (logos, payment screenshots, documents)

With BACKUP_ENCRYPTION_KEY set (base64 of 32 random bytes) the archive is encrypted with AES-256-GCM in 1 MiB
chunks; every chunk is authenticated and the last one is marked, so a truncated, reordered or altered file is
rejected instead of half-restored. Keep that key somewhere other than the server: without it the backup is
unreadable, which is the point.

With BACKUP_S3_BUCKET set, each new backup is also copied to that S3-compatible bucket (off-site copy).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, func, inspect, select, table, text
from sqlalchemy.engine import make_url

MAGIC = b"APBACKUP1\n"
CHUNK = 1024 * 1024
NAME_PREFIX = "backup-"
COUNTED_TABLES = ("organizations", "users", "customers", "appointments", "payments", "payment_refunds", "customer_documents")


class BackupError(RuntimeError):
    pass


@dataclass
class BackupConfig:
    database_url: str
    uploads_dir: Path | None
    backup_dir: Path
    encryption_key: bytes | None = None
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    s3_bucket: str | None = None
    s3_prefix: str = "backups/"
    s3_client_factory: Callable[[], Any] | None = field(default=None, repr=False)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def config_from_settings() -> BackupConfig:
    """From backend/.env or the environment (Docker passes the root .env as environment variables)."""
    from app.core.storage import active_backend
    from app.services.platform_config import runtime_settings

    s = runtime_settings()  # .env, with values saved in Super admin -> Integrations on top
    return BackupConfig(
        database_url=s.database_url,
        uploads_dir=Path(s.storage_local_path) if active_backend() == "local" else None,
        backup_dir=Path(s.backup_dir or (Path(s.storage_local_path).parent / "backups")),
        encryption_key=decode_key(s.backup_encryption_key) if s.backup_encryption_key else None,
        keep_daily=s.backup_keep_daily,
        keep_weekly=s.backup_keep_weekly,
        keep_monthly=s.backup_keep_monthly,
        s3_bucket=s.backup_s3_bucket or None,
        s3_prefix=s.backup_s3_prefix,
        s3_client_factory=_s3_client_from_settings,
    )


def _s3_client_from_settings():
    from app.core.storage import s3_client

    return s3_client()


def decode_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise BackupError("BACKUP_ENCRYPTION_KEY is not valid base64.") from exc
    if len(key) != 32:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be base64 of exactly 32 random bytes.")
    return key


# ----------------------------------------------------------------------------------------------- helpers
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _pg_args(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Connection flags for pg_dump/pg_restore. The password goes in the environment, never on the command line."""
    url = make_url(database_url)
    args = ["-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "postgres", "-d", url.database or ""]
    env = {**os.environ}
    if url.password:
        env["PGPASSWORD"] = url.password
    return args, env


def _run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    # pg_dump / pg_restore with fixed argument lists, never through a shell (hence the nosec markers).
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # nosec B603
    except FileNotFoundError as exc:
        raise BackupError(f"{cmd[0]} is not installed (install the PostgreSQL client tools, version >= the server).") from exc
    if proc.returncode != 0:
        raise BackupError(f"{cmd[0]} failed: {proc.stderr.strip()[-500:]}")


def _schema_info(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            names = set(inspect(conn).get_table_names())
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if "alembic_version" in names else None
            counts = {t: int(conn.execute(select(func.count()).select_from(table(t))).scalar() or 0)
                      for t in COUNTED_TABLES if t in names}
    finally:
        engine.dispose()
    return {"alembic_revision": revision, "row_counts": counts}


def _sqlite_path(database_url: str) -> Path:
    path = make_url(database_url).database
    if not path:
        raise BackupError("In-memory SQLite databases cannot be backed up.")
    return Path(path)


# ----------------------------------------------------------------------------------------------- encryption
def encrypt_file(src: Path, dst: Path, key: bytes) -> None:
    aes = AESGCM(key)
    file_id = os.urandom(8)
    size = src.stat().st_size
    with src.open("rb") as fin, dst.open("wb") as fout:
        fout.write(MAGIC + file_id)
        index, sent = 0, 0
        while True:
            block = fin.read(CHUNK)
            sent += len(block)
            last = sent >= size
            nonce = file_id + struct.pack(">I", index)
            ct = aes.encrypt(nonce, block, b"\x01" if last else b"\x00")
            fout.write(struct.pack(">I", len(ct)) + ct)
            index += 1
            if last:
                break


def _open_chunk(aes: AESGCM, nonce: bytes, ct: bytes) -> tuple[bytes, bool] | None:
    """Decrypt one chunk; returns (data, is_last) or None when it fails authentication under both markers."""
    try:
        return aes.decrypt(nonce, ct, b"\x00"), False
    except InvalidTag:
        try:
            return aes.decrypt(nonce, ct, b"\x01"), True
        except InvalidTag:
            return None


def decrypt_file(src: Path, dst: Path, key: bytes) -> None:
    aes = AESGCM(key)
    with src.open("rb") as fin, dst.open("wb") as fout:
        if fin.read(len(MAGIC)) != MAGIC:
            raise BackupError("Not an encrypted backup (or a different format).")
        file_id = fin.read(8)
        index, finished = 0, False
        while True:
            header = fin.read(4)
            if not header:
                break
            if finished:
                raise BackupError("Encrypted backup has data after its final chunk.")
            (length,) = struct.unpack(">I", header)
            ct = fin.read(length)
            opened = _open_chunk(aes, file_id + struct.pack(">I", index), ct)
            if opened is None:
                raise BackupError("Backup cannot be decrypted: wrong BACKUP_ENCRYPTION_KEY, or the file was altered.")
            plain, finished = opened
            fout.write(plain)
            index += 1
        if not finished:
            raise BackupError("Encrypted backup is truncated (final chunk missing).")


# ----------------------------------------------------------------------------------------------- create
def create(cfg: BackupConfig, *, now: datetime | None = None) -> Path:
    now = now or datetime.now(UTC)
    cfg.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory(prefix="backup-") as tmp:
        work = Path(tmp)
        files: dict[str, dict[str, Any]] = {}
        if cfg.is_sqlite:
            db_file = work / "database.sqlite"
            src = sqlite3.connect(_sqlite_path(cfg.database_url))
            dst = sqlite3.connect(db_file)
            try:
                src.backup(dst)  # consistent snapshot while the app keeps writing
            finally:
                dst.close()
                src.close()
        else:
            db_file = work / "database.dump"
            args, env = _pg_args(cfg.database_url)
            _run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "-f", str(db_file), *args], env)
        files[db_file.name] = {"sha256": _sha256(db_file), "size": db_file.stat().st_size}

        upload_files: list[Path] = []
        if cfg.uploads_dir and cfg.uploads_dir.exists():
            upload_files = [p for p in sorted(cfg.uploads_dir.rglob("*")) if p.is_file()]
            for p in upload_files:
                files["uploads/" + p.relative_to(cfg.uploads_dir).as_posix()] = {"sha256": _sha256(p), "size": p.stat().st_size}

        manifest = {
            "format": 1,
            "created_at": now.isoformat(),
            "database": "sqlite" if cfg.is_sqlite else "postgresql",
            **_schema_info(cfg.database_url),
            "uploads_included": cfg.uploads_dir is not None,
            "encrypted": cfg.encryption_key is not None,
            "files": files,
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2))

        archive = work / f"{NAME_PREFIX}{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(work / "manifest.json", arcname="manifest.json")
            tar.add(db_file, arcname=db_file.name)
            for p in upload_files:
                tar.add(p, arcname="uploads/" + p.relative_to(cfg.uploads_dir).as_posix())

        final = cfg.backup_dir / (archive.name + (".enc" if cfg.encryption_key else ""))
        partial = final.with_name(final.name + ".partial")
        if cfg.encryption_key:
            encrypt_file(archive, partial, cfg.encryption_key)
        else:
            shutil.copyfile(archive, partial)
        partial.replace(final)  # never leave a half-written file under the final name
    if cfg.s3_bucket and cfg.s3_client_factory:
        cfg.s3_client_factory().upload_file(str(final), cfg.s3_bucket, cfg.s3_prefix + final.name)
    return final


# ----------------------------------------------------------------------------------------------- verify / open
def _open_archive(path: Path, key: bytes | None, work: Path) -> Path:
    if path.name.endswith(".enc"):
        if not key:
            raise BackupError("This backup is encrypted: set BACKUP_ENCRYPTION_KEY.")
        plain = work / "archive.tar.gz"
        decrypt_file(path, plain, key)
        path = plain
    extract = work / "extracted"
    extract.mkdir()
    try:
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(extract, filter="data")  # refuses absolute paths, "..", links outside the folder
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise BackupError(f"Archive is damaged: {exc}") from exc
    return extract


def verify(path: Path, key: bytes | None = None) -> dict[str, Any]:
    """Open the backup and prove it is restorable without touching the live system."""
    with tempfile.TemporaryDirectory(prefix="verify-") as tmp:
        extract = _open_archive(path, key, Path(tmp))
        manifest_path = extract / "manifest.json"
        if not manifest_path.exists():
            raise BackupError("manifest.json missing from backup.")
        manifest = json.loads(manifest_path.read_text())
        for name, meta in manifest["files"].items():
            f = extract / name
            if not f.exists():
                raise BackupError(f"{name} is listed in the manifest but missing.")
            if _sha256(f) != meta["sha256"]:
                raise BackupError(f"{name} does not match its checksum.")
        if manifest["database"] == "sqlite":
            con = sqlite3.connect(extract / "database.sqlite")
            try:
                result = con.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                con.close()
            if result != "ok":
                raise BackupError(f"SQLite integrity check failed: {result}")
        else:
            _run(["pg_restore", "--list", str(extract / "database.dump")])
        return manifest


# ----------------------------------------------------------------------------------------------- restore
def restore(path: Path, cfg: BackupConfig, *, restore_uploads: bool = True) -> dict[str, Any]:
    """Replace the live database (and uploads) with the backup. Stop the API and worker first.

    The current data is kept beside the original (``*.before-restore-<stamp>``) for SQLite and uploads, so a
    mistaken restore can be undone. For PostgreSQL take a fresh backup first (the CLI does this for you)."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory(prefix="restore-") as tmp:
        manifest = verify(path, cfg.encryption_key)  # never restore something that does not verify
        extract = _open_archive(path, cfg.encryption_key, Path(tmp))
        if (manifest["database"] == "sqlite") != cfg.is_sqlite:
            raise BackupError(f"Backup is {manifest['database']} but DATABASE_URL points to {'sqlite' if cfg.is_sqlite else 'postgresql'}.")
        if cfg.is_sqlite:
            live = _sqlite_path(cfg.database_url)
            live.parent.mkdir(parents=True, exist_ok=True)
            if live.exists():
                shutil.copy2(live, live.with_name(f"{live.name}.before-restore-{stamp}"))
            for suffix in ("-wal", "-shm"):
                Path(str(live) + suffix).unlink(missing_ok=True)
            src = sqlite3.connect(extract / "database.sqlite")
            dst = sqlite3.connect(live)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        else:
            args, env = _pg_args(cfg.database_url)
            _run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction", *args,
                  str(extract / "database.dump")], env)
        if restore_uploads and cfg.uploads_dir and (extract / "uploads").exists():
            if cfg.uploads_dir.exists():
                cfg.uploads_dir.rename(cfg.uploads_dir.with_name(f"{cfg.uploads_dir.name}.before-restore-{stamp}"))
            shutil.copytree(extract / "uploads", cfg.uploads_dir)
    return manifest


# ----------------------------------------------------------------------------------------------- retention
def _stamp(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name[len(NAME_PREFIX):len(NAME_PREFIX) + 15], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def list_backups(cfg: BackupConfig) -> list[Path]:
    if not cfg.backup_dir.exists():
        return []
    found = [p for p in cfg.backup_dir.iterdir() if p.name.startswith(NAME_PREFIX) and p.name.endswith((".tar.gz", ".tar.gz.enc")) and _stamp(p)]
    return sorted(found, key=lambda p: _stamp(p), reverse=True)


def prune(cfg: BackupConfig) -> list[Path]:
    """Keep the newest backup of each of the last N days, ISO weeks and months; delete the rest.

    The newest backup is always kept, whatever the settings."""
    backups = list_backups(cfg)
    keep: set[Path] = set(backups[:1])
    for keyfn, limit in ((lambda d: d.date(), cfg.keep_daily), (lambda d: d.isocalendar()[:2], cfg.keep_weekly), (lambda d: (d.year, d.month), cfg.keep_monthly)):
        seen: list[Any] = []
        for p in backups:
            bucket = keyfn(_stamp(p))
            if bucket not in seen:
                if len(seen) >= limit:
                    break
                seen.append(bucket)
                keep.add(p)
    removed = [p for p in backups if p not in keep]
    for p in removed:
        p.unlink()
    return removed


# ----------------------------------------------------------------------------------------------- CLI
def _record(info: dict[str, Any]) -> None:
    """Tell the app the outcome, for the status page and alerts. Never fails the backup itself."""
    try:
        from app.core.database import session_scope
        from app.services.ops_service import record_backup

        with session_scope() as db:
            record_backup(db, info)
    except Exception as exc:  # pragma: no cover - database down at backup time
        print(f"warning: could not record backup status: {exc}", file=sys.stderr)


def run_backup(cfg: BackupConfig) -> Path:
    """Create, verify, prune and record the outcome (success or failure) for the status page and alerts."""
    started = datetime.now(UTC)
    try:
        path = create(cfg)
        manifest = verify(path, cfg.encryption_key)
    except Exception as exc:
        _record({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]})
        raise
    removed = prune(cfg)
    _record({"ok": True, "file": path.name, "size_bytes": path.stat().st_size, "encrypted": bool(cfg.encryption_key),
             "offsite": bool(cfg.s3_bucket), "seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
             "pruned": len(removed), "row_counts": manifest["row_counts"]})
    return path


def next_run(now: datetime, at: str, tz: str) -> datetime:
    """The next occurrence of local time ``at`` (HH:MM) in time zone ``tz`` strictly after ``now``."""
    from datetime import time, timedelta
    from zoneinfo import ZoneInfo

    hour, minute = (int(x) for x in at.split(":"))
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    candidate = datetime.combine(local.date(), time(hour, minute), tzinfo=zone)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), time(hour, minute), tzinfo=zone)
    return candidate.astimezone(UTC)


def schedule(cfg: BackupConfig, at: str, tz: str, *, max_runs: int | None = None, sleep=None) -> int:
    """Run a backup every day at ``at`` local time until SIGTERM. A failed night is recorded and retried the next."""
    import signal
    import time as _time

    sleep = sleep or _time.sleep
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    runs = 0
    print(f"Backups scheduled daily at {at} ({tz}).", flush=True)
    while not stopping["flag"] and (max_runs is None or runs < max_runs):
        due = next_run(datetime.now(UTC), at, tz)
        while not stopping["flag"] and datetime.now(UTC) < due:
            sleep(min(30.0, max(0.0, (due - datetime.now(UTC)).total_seconds())))
        if stopping["flag"]:
            break
        try:
            path = run_backup(cfg)
            print(f"Backup written and verified: {path.name}", flush=True)
        except Exception as exc:  # recorded by run_backup; keep the schedule alive
            print(f"Backup failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        runs += 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ops.backup", description="Create, verify, restore and prune backups.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="back up the database and uploads now, then prune old backups")
    v = sub.add_parser("verify", help="check that a backup is complete and readable")
    v.add_argument("file", type=Path)
    r = sub.add_parser("restore", help="replace the live data with a backup (stop the API and worker first)")
    r.add_argument("file", type=Path)
    r.add_argument("--yes", action="store_true", help="confirm that the current data will be replaced")
    r.add_argument("--skip-uploads", action="store_true")
    sc = sub.add_parser("schedule", help="stay running and back up once a day (for the Docker backup service)")
    sc.add_argument("--at", default=None, help="local time HH:MM (default BACKUP_AT, 02:30; zone BACKUP_TIMEZONE, Asia/Kolkata)")
    sub.add_parser("prune", help="delete backups outside the retention policy")
    sub.add_parser("list", help="list local backups, newest first")
    args = parser.parse_args(argv)
    cfg = config_from_settings()
    try:
        if args.command == "create":
            path = run_backup(cfg)
            print(f"Backup written and verified: {path} ({path.stat().st_size:,} bytes).")
        elif args.command == "schedule":
            from app.core.config import get_settings

            return schedule(cfg, args.at or get_settings().backup_at, get_settings().backup_timezone)
        elif args.command == "verify":
            manifest = verify(args.file, cfg.encryption_key)
            print(f"OK: {manifest['database']} backup from {manifest['created_at']}, schema {manifest['alembic_revision']}, "
                  f"{len(manifest['files'])} files, rows {manifest['row_counts']}")
        elif args.command == "restore":
            if not args.yes:
                print("Restoring replaces the current database and uploads. Stop the API and worker, then re-run with --yes.")
                return 2
            if not cfg.is_sqlite:
                safety = create(cfg)
                print(f"Safety backup of the current data: {safety}")
            manifest = restore(args.file, cfg, restore_uploads=not args.skip_uploads)
            print(f"Restored backup from {manifest['created_at']} (schema {manifest['alembic_revision']}). "
                  "Run `alembic upgrade head`, then start the API and worker.")
        elif args.command == "prune":
            removed = prune(cfg)
            print(f"Removed {len(removed)} backup(s).")
        elif args.command == "list":
            for p in list_backups(cfg):
                print(f"{p.name}\t{p.stat().st_size:,} bytes")
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
