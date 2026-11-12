"""Create or promote a platform super admin.

Usage (from backend/ with the virtualenv active):
    python ../scripts/create_platform_admin.py --email admin@example.com --name "Platform Admin"
The password is prompted (or read from PLATFORM_ADMIN_PASSWORD) and never echoed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import session_scope  # noqa: E402
from app.core.enums import UserStatus  # noqa: E402
from app.core.time import utcnow  # noqa: E402
from app.models import User  # noqa: E402
from app.repositories.users import UserRepository  # noqa: E402
from app.security.identifiers import normalize_email  # noqa: E402
from app.security.passwords import hash_password, validate_password_policy  # noqa: E402
from app.services.seed import seed_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Admin")
    args = parser.parse_args()
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    validate_password_policy(password)
    email = normalize_email(args.email)
    with session_scope() as db:
        seed_all(db)
        repo = UserRepository(db)
        user = repo.get_by_email(email)
        if user is None:
            user = User(full_name=args.name, email=email, status=UserStatus.ACTIVE, email_verified_at=utcnow())
            db.add(user)
        user.password_hash = hash_password(password)
        user.is_platform_admin = True
        user.status = UserStatus.ACTIVE
        db.flush()
        print(f"Platform admin ready: {email} ({user.public_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
