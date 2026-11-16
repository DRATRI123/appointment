"""One-shot release step: ``python -m app.ops.setup``.

Applies database migrations, then seeds roles and permissions (idempotent; grants permissions added by a new release
to the built-in roles). Run it before starting a new version of the API and worker; the Docker stack does this in its
``migrate`` service.
"""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.core.config import BASE_DIR
from app.core.logging import configure_logging, get_logger

AT_REST_MARKER = "privacy.encrypted_at_rest_v1"


def encrypt_existing_data_once(log) -> None:
    """One-time migration: encrypt records and private files stored before at-rest encryption covered them.
    Idempotent and batched (app.ops.rotate_keys); deploy.sh has taken a verified backup before any migration."""
    from sqlalchemy import select

    from app.core.database import session_scope
    from app.core.time import utcnow
    from app.models import SystemSetting
    from app.ops.rotate_keys import rotate

    with session_scope() as db:
        if db.scalar(select(SystemSetting.id).where(SystemSetting.key == AT_REST_MARKER)):
            return
    report = rotate()
    failed = sum(c["failed"] for c in report.values())
    changed = {k: c["reencrypted"] for k, c in report.items() if c["reencrypted"]}
    log.info("setup.encrypted_existing_data", changed=changed, failed=failed)
    if failed:
        print(f"{failed} stored value(s) could not be decrypted and were left unchanged: run python -m app.ops.rotate_keys --dry-run")
        return  # try again next time, after the operator has added the missing old key
    with session_scope() as db:
        db.add(SystemSetting(key=AT_REST_MARKER, value={"at": utcnow().isoformat(), "changed": changed}))


def main() -> int:
    configure_logging()
    log = get_logger("setup")
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    command.upgrade(cfg, "head")
    log.info("setup.migrated")

    from app.core.database import session_scope
    from app.services.seed import seed_all

    with session_scope() as db:
        seed_all(db)
    log.info("setup.seeded")
    encrypt_existing_data_once(log)
    print("Database migrated and roles/permissions up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
