"""Create the platform super admin, or recover access to it. Run on the server; there is no web page for this.

    python -m app.ops.platform_admin --email admin@clinic.com                 # first-time set-up
    python -m app.ops.platform_admin --email admin@clinic.com --recover       # lost password or authenticator

Rules (docs/superadmin-setup.md):
* There is no default super admin, password or sign-up page. Only someone with shell access to the server can run
  this, which is the same trust as reading the database.
* First set-up creates a new account. If a super admin already exists, creating another needs ``--add-another``.
* An existing ordinary account is never promoted silently: that needs ``--promote-existing``.
* ``--recover`` sets a new password for an existing super admin, turns off their two-step sign-in (they set it up
  again at the next sign-in, as it is required) and signs out all their devices.
* The password is typed at a hidden prompt (or read from PLATFORM_ADMIN_PASSWORD for automation), checked against
  the password policy, stored only as an Argon2id hash, and never printed or logged. Every run is audit-logged.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import func, select, update

from app.core.database import session_scope
from app.core.enums import UserStatus
from app.core.exceptions import AppError
from app.core.time import utcnow
from app.models import User, UserSession
from app.repositories.users import UserRepository
from app.security.identifiers import normalize_email
from app.security.passwords import hash_password, validate_password_policy
from app.services.audit_service import record_audit
from app.services.seed import seed_all


class Refused(RuntimeError):
    pass


MIN_LENGTH = 12  # stricter than ordinary accounts


def _checked(password: str) -> str:
    validate_password_policy(password)
    if len(password) < MIN_LENGTH:
        raise Refused(f"A super admin password needs at least {MIN_LENGTH} characters.")
    return password


def _password() -> str:
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Type it again: ") != password:
            raise Refused("The two passwords are different.")
    return _checked(password)


def run(email: str, name: str, *, recover: bool = False, add_another: bool = False, promote_existing: bool = False,
        password: str | None = None) -> str:
    email = normalize_email(email)
    with session_scope() as db:
        seed_all(db)
        user = UserRepository(db).get_by_email(email)
        admins = db.scalar(select(func.count()).select_from(User).where(User.is_platform_admin.is_(True), User.deleted_at.is_(None))) or 0
        now = utcnow()
        if recover:
            if user is None or not user.is_platform_admin:
                raise Refused(f"{email} is not a super admin. Recovery only works for an existing super admin.")
            user.password_hash = hash_password(_checked(password) if password else _password())
            user.mfa_secret = user.mfa_enabled_at = user.mfa_last_step = user.mfa_recovery_hashes = None
            user.failed_login_attempts, user.locked_until, user.status = 0, None, UserStatus.ACTIVE
            db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=now))
            record_audit(db, action="platform.admin_recovered", actor=None, entity_type="user", entity_id=user.public_id,
                         after={"email": email, "mfa_reset": True, "sessions_revoked": True})
            return f"Recovered {email}: new password set, two-step sign-in reset (set it up again at sign-in), all devices signed out."
        if user is not None and user.is_platform_admin:
            raise Refused(f"{email} is already a super admin. To reset its password or authenticator use --recover.")
        if admins and not add_another:
            raise Refused("A super admin already exists. To add a second one on purpose, run again with --add-another.")
        if user is not None and not promote_existing:
            raise Refused(f"{email} already has an ordinary account. To make it a super admin on purpose, add --promote-existing.")
        pw = hash_password(_checked(password) if password else _password())
        if user is None:
            user = User(full_name=name, email=email, status=UserStatus.ACTIVE, email_verified_at=now)
            db.add(user)
        user.password_hash, user.is_platform_admin, user.status = pw, True, UserStatus.ACTIVE
        db.flush()
        record_audit(db, action="platform.admin_created", actor=None, entity_type="user", entity_id=user.public_id,
                     after={"email": email, "promoted_existing": promote_existing, "additional": bool(admins)})
        return (f"Super admin ready: {email}. Sign in, then turn on two-step sign-in under Profile & security "
                "(required before the super admin pages open).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ops.platform_admin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Admin")
    parser.add_argument("--recover", action="store_true", help="new password + reset two-step sign-in for an existing super admin")
    parser.add_argument("--add-another", action="store_true", help="allow a second super admin")
    parser.add_argument("--promote-existing", action="store_true", help="make an existing ordinary account a super admin")
    args = parser.parse_args(argv)
    try:
        print(run(args.email, args.name, recover=args.recover, add_another=args.add_another, promote_existing=args.promote_existing))
    except Refused as exc:
        print(f"Not done: {exc}", file=sys.stderr)
        return 1
    except AppError as exc:  # password policy
        print(f"Not done: {exc.detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
