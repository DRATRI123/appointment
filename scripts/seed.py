"""Seed permissions, system roles and platform settings.

Usage (from backend/ with the virtualenv active):
    python ../scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import session_scope  # noqa: E402
from app.services.seed import seed_all  # noqa: E402

if __name__ == "__main__":
    with session_scope() as db:
        seed_all(db)
    print("Seeded permissions, system roles and system settings.")
    # One time only: encrypt records and private files saved before at-rest encryption covered them.
    from app.core.logging import get_logger  # noqa: E402
    from app.ops.setup import encrypt_existing_data_once  # noqa: E402

    encrypt_existing_data_once(get_logger("seed"))
