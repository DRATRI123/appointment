"""Online backup of the SQLite development database using the SQLite backup API.

Usage:
    python scripts/backup_sqlite.py [destination_dir]
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "backend" / "data" / "app.db"


def main() -> int:
    if not SOURCE.exists():
        print(f"No database at {SOURCE}")
        return 1
    dest_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"app-{stamp}.db"
    with sqlite3.connect(SOURCE) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    print(f"Backup written to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
