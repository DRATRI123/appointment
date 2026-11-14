"""Create or promote a platform super admin (wrapper around ``python -m app.ops.platform_admin``).

Usage (from backend/ with the virtualenv active):
    python ../scripts/create_platform_admin.py --email admin@example.com --name "Platform Admin"
In Docker:
    docker compose run --rm api python -m app.ops.platform_admin --email admin@example.com
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ops.platform_admin import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
