"""Create or promote a platform super admin: ``python -m app.ops.platform_admin --email admin@example.com``.

The password is prompted (or read from PLATFORM_ADMIN_PASSWORD) and never echoed or logged.
"""
from __future__ import annotations

import argparse
import getpass
import os

from app.core.database import session_scope
from app.core.enums import UserStatus
from app.core.time import utcnow
from app.models import User
from app.repositories.users import UserRepository
from app.security.identifiers import normalize_email
from app.security.passwords import hash_password, validate_password_policy
from app.services.seed import seed_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Admin")
    args = parser.parse_args(argv)
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
