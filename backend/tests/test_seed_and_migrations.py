from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.enums import SystemRole
from app.models import Permission, Role
from app.security.permissions import PERMISSIONS
from app.services.seed import seed_all

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_seed_is_idempotent(db):
    seed_all(db)
    seed_all(db)
    perms = db.scalars(select(Permission)).all()
    roles = db.scalars(select(Role).where(Role.is_system.is_(True))).all()
    assert len(perms) == len(PERMISSIONS)
    assert {r.code for r in roles} == {r.value for r in SystemRole}
    owner = next(r for r in roles if r.code == SystemRole.ORG_OWNER)
    codes = {p.code for p in owner.permissions}
    assert "payments:verify" in codes
    assert not any(c.startswith("platform:") for c in codes)


def test_alembic_upgrade_and_downgrade_on_fresh_sqlite(tmp_path):
    db_file = tmp_path / "mig.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "APP_ENV": "test"}
    for args in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"
