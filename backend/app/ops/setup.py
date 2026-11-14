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
    print("Database migrated and roles/permissions up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
