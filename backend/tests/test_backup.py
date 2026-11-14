"""Backup, verify, restore and retention, on real files (and a real PostgreSQL when TEST_POSTGRES_URL is set)."""
from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import create_engine, text

from app.ops import backup as bk

KEY = os.urandom(32)


def _live_sqlite(tmp_path: Path) -> tuple[str, Path]:
    db = tmp_path / "live" / "app.db"
    db.parent.mkdir()
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE alembic_version (version_num TEXT);
        INSERT INTO alembic_version VALUES ('7524363447e0');
        CREATE TABLE organizations (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO organizations (name) VALUES ('Sunrise Ayurveda'), ('Lotus Clinic');
        CREATE TABLE payments (id INTEGER PRIMARY KEY, amount_paise INTEGER);
        INSERT INTO payments (amount_paise) VALUES (50000);
    """)
    con.commit()
    con.close()
    uploads = tmp_path / "live" / "uploads"
    (uploads / "private" / "org1").mkdir(parents=True)
    (uploads / "private" / "org1" / "screenshot.png").write_bytes(b"\x89PNG fake screenshot")
    (uploads / "public").mkdir()
    (uploads / "public" / "logo.png").write_bytes(b"\x89PNG logo")
    return f"sqlite:///{db.as_posix()}", uploads


def _cfg(tmp_path: Path, url: str, uploads: Path | None, key: bytes | None = KEY, **kw) -> bk.BackupConfig:
    return bk.BackupConfig(database_url=url, uploads_dir=uploads, backup_dir=tmp_path / "backups", encryption_key=key, **kw)


@pytest.mark.parametrize("key", [KEY, None], ids=["encrypted", "plain"])
def test_sqlite_backup_round_trip_restores_database_and_uploads(tmp_path, key):
    url, uploads = _live_sqlite(tmp_path)
    cfg = _cfg(tmp_path, url, uploads, key)
    path = bk.create(cfg)
    assert path.name.endswith(".tar.gz.enc" if key else ".tar.gz")
    if key:  # nothing readable without the key
        assert b"Sunrise" not in path.read_bytes() and b"screenshot" not in path.read_bytes()
    manifest = bk.verify(path, key)
    assert manifest["alembic_revision"] == "7524363447e0"
    assert manifest["row_counts"] == {"organizations": 2, "payments": 1}
    assert set(manifest["files"]) == {"database.sqlite", "uploads/private/org1/screenshot.png", "uploads/public/logo.png"}

    # Disaster: data changed and a file lost.
    con = sqlite3.connect(url.removeprefix("sqlite:///"))
    con.execute("DELETE FROM organizations")
    con.commit()
    con.close()
    (uploads / "public" / "logo.png").unlink()

    bk.restore(path, cfg)
    con = sqlite3.connect(url.removeprefix("sqlite:///"))
    assert [r[0] for r in con.execute("SELECT name FROM organizations ORDER BY id")] == ["Sunrise Ayurveda", "Lotus Clinic"]
    con.close()
    assert (uploads / "public" / "logo.png").read_bytes() == b"\x89PNG logo"
    # The state before the restore is kept so a mistaken restore can be undone.
    assert list((tmp_path / "live").glob("app.db.before-restore-*")) and list((tmp_path / "live").glob("uploads.before-restore-*"))


def test_encrypted_backups_reject_wrong_key_tampering_and_truncation(tmp_path):
    url, uploads = _live_sqlite(tmp_path)
    path = bk.create(_cfg(tmp_path, url, uploads))
    with pytest.raises(bk.BackupError, match="encrypted"):
        bk.verify(path, None)
    with pytest.raises(bk.BackupError, match="wrong BACKUP_ENCRYPTION_KEY"):
        bk.verify(path, os.urandom(32))

    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    tampered = tmp_path / "tampered.tar.gz.enc"
    tampered.write_bytes(bytes(data))
    with pytest.raises(bk.BackupError, match="altered"):
        bk.verify(tampered, KEY)

    truncated = tmp_path / "truncated.tar.gz.enc"
    plain = tmp_path / "big.bin"
    plain.write_bytes(os.urandom(bk.CHUNK * 2 + 10))  # three chunks
    bk.encrypt_file(plain, truncated, KEY)
    whole = truncated.read_bytes()
    first_two = len(bk.MAGIC) + 8 + 2 * (4 + bk.CHUNK + 16)
    truncated.write_bytes(whole[:first_two])  # drop the final chunk cleanly
    with pytest.raises(bk.BackupError, match="truncated"):
        bk.decrypt_file(truncated, tmp_path / "out.bin", KEY)
    out = tmp_path / "ok.bin"
    bk.encrypt_file(plain, truncated, KEY)
    bk.decrypt_file(truncated, out, KEY)
    assert out.read_bytes() == plain.read_bytes()


def test_verify_catches_a_file_that_does_not_match_its_checksum(tmp_path):
    url, uploads = _live_sqlite(tmp_path)
    path = bk.create(_cfg(tmp_path, url, uploads, key=None))
    repacked = tmp_path / "backups" / "backup-20200101-000000.tar.gz"
    with tarfile.open(path, "r:gz") as src, tarfile.open(repacked, "w:gz") as dst:
        for member in src.getmembers():
            data = src.extractfile(member).read()
            if member.name == "uploads/public/logo.png":
                data = b"swapped"
                member.size = len(data)
            dst.addfile(member, io.BytesIO(data))
    with pytest.raises(bk.BackupError, match="checksum"):
        bk.verify(repacked)


def test_archives_cannot_write_outside_the_extraction_folder(tmp_path):
    evil = tmp_path / "backup-20200101-000000.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        info = tarfile.TarInfo("../../escaped.txt")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"bad"))
        manifest = json.dumps({"files": {}, "database": "sqlite"}).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
    with pytest.raises(bk.BackupError, match="damaged"):
        bk.verify(evil)
    assert not list(tmp_path.parent.glob("escaped.txt"))


def test_restore_refuses_a_backup_for_the_other_database_kind(tmp_path):
    url, uploads = _live_sqlite(tmp_path)
    path = bk.create(_cfg(tmp_path, url, uploads))
    with pytest.raises(bk.BackupError, match="DATABASE_URL points to postgresql"):
        bk.restore(path, _cfg(tmp_path, "postgresql+psycopg://u:p@localhost/x", uploads))


def test_retention_keeps_daily_weekly_and_monthly_copies(tmp_path):
    cfg = _cfg(tmp_path, "sqlite:///unused.db", None, keep_daily=7, keep_weekly=4, keep_monthly=6)
    cfg.backup_dir.mkdir()
    start = datetime(2026, 11, 14, 2, 0, tzinfo=UTC)
    for day in range(200):  # one backup a night for 200 nights, plus an extra one today
        stamp = (start - timedelta(days=day)).strftime("%Y%m%d-%H%M%S")
        (cfg.backup_dir / f"backup-{stamp}.tar.gz.enc").write_bytes(b"x")
    (cfg.backup_dir / "backup-20261114-140000.tar.gz.enc").write_bytes(b"x")
    (cfg.backup_dir / "notes.txt").write_text("not a backup")
    bk.prune(cfg)
    left = [p.name for p in bk.list_backups(cfg)]
    assert left[0] == "backup-20261114-140000.tar.gz.enc"  # newest is always kept
    assert len(left) <= 7 + 4 + 6 and len(left) >= 7 + 4
    assert "backup-20261108-020000.tar.gz.enc" in left  # within the last 7 days
    assert any(n.startswith("backup-202606") for n in left)  # a monthly copy from five months ago
    assert not any(n.startswith("backup-202604") for n in left)  # older than six months is gone
    assert (cfg.backup_dir / "notes.txt").exists()


@mock_aws
def test_new_backups_are_copied_off_site(tmp_path):
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket="clinic-backups", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    url, uploads = _live_sqlite(tmp_path)
    cfg = _cfg(tmp_path, url, uploads, s3_bucket="clinic-backups", s3_prefix="nightly/",
               s3_client_factory=lambda: boto3.client("s3", region_name="ap-south-1"))
    path = bk.create(cfg)
    obj = s3.get_object(Bucket="clinic-backups", Key=f"nightly/{path.name}")
    assert obj["Body"].read() == path.read_bytes()


def test_cli_create_verifies_prunes_and_records_the_outcome(tmp_path, monkeypatch, capsys):
    url, uploads = _live_sqlite(tmp_path)
    cfg = _cfg(tmp_path, url, uploads)
    recorded = []
    monkeypatch.setattr(bk, "config_from_settings", lambda: cfg)
    monkeypatch.setattr(bk, "_record", recorded.append)
    assert bk.main(["create"]) == 0
    assert recorded[-1]["ok"] is True and recorded[-1]["encrypted"] is True and recorded[-1]["row_counts"]["organizations"] == 2
    assert bk.main(["list"]) == 0 and "backup-" in capsys.readouterr().out
    # Restore needs explicit confirmation.
    assert bk.main(["restore", str(bk.list_backups(cfg)[0])]) == 2
    # A failing backup is recorded as a failure.
    monkeypatch.setattr(bk, "config_from_settings", lambda: _cfg(tmp_path, "sqlite:///" + (tmp_path / "missing" / "x.db").as_posix(), None))
    with pytest.raises(Exception):  # noqa: B017 - any error; the point is what gets recorded
        bk.main(["create"])
    assert recorded[-1]["ok"] is False


def test_bad_encryption_keys_are_rejected():
    with pytest.raises(bk.BackupError, match="32"):
        bk.decode_key(base64.b64encode(b"short").decode())
    with pytest.raises(bk.BackupError, match="base64"):
        bk.decode_key("not base64 !!")


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL to a scratch PostgreSQL database")
def test_postgres_backup_round_trip(tmp_path):
    url = os.environ["TEST_POSTGRES_URL"]
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS organizations, alembic_version"))
        conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('7524363447e0')"))
        conn.execute(text("CREATE TABLE organizations (id serial primary key, name text)"))
        conn.execute(text("INSERT INTO organizations (name) VALUES ('Sunrise Ayurveda')"))
    cfg = _cfg(tmp_path, url, None)
    path = bk.create(cfg)
    assert bk.verify(path, KEY)["row_counts"] == {"organizations": 1}
    with engine.begin() as conn:
        conn.execute(text("UPDATE organizations SET name = 'Wrong'"))
        conn.execute(text("INSERT INTO organizations (name) VALUES ('Extra')"))
    bk.restore(path, cfg)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM organizations")).scalars().all() == ["Sunrise Ayurveda"]
    engine.dispose()
