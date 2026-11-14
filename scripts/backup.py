"""Backups from the command line (Windows or Linux). Run from backend/ with the virtualenv active:

    python ..\\scripts\\backup.py create
    python ..\\scripts\\backup.py verify ..\\backups\\backup-20261114-020000.tar.gz.enc
    python ..\\scripts\\backup.py restore <file> --yes
    python ..\\scripts\\backup.py list

Same as ``python -m app.ops.backup``; see backend/app/ops/backup.py and documentation/deployment.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ops.backup import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
