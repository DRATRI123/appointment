"""Which database migrations are waiting, and could any of them delete data? ``python -m app.ops.migration_check``

deploy.sh runs this before migrating. Exit codes:
    0  up to date, or every pending migration only adds things (tables, columns, indexes)
    3  a pending migration removes or rewrites data (drops a table or column, changes a column type, or runs
       DELETE / TRUNCATE / DROP in raw SQL): deploy.sh then stops and asks for explicit confirmation
    1  the check itself failed (for example the database is unreachable)

Only each migration's upgrade() step is inspected; downgrade() steps contain drops by nature and never run on deploy.
A migration whose upgrade() is destructive on purpose stays flagged: the person deploying decides, after a backup.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from dataclasses import asdict, dataclass

DESTRUCTIVE_PATTERNS = {
    "drops a table": re.compile(r"\bop\.drop_table\s*\("),
    "drops a column": re.compile(r"\b(op|batch_op)\.drop_column\s*\("),
    "changes a column type": re.compile(r"\b(op|batch_op)\.alter_column\s*\([^)]*\btype_\s*=", re.S),
    "runs DELETE/TRUNCATE/DROP SQL": re.compile(r"\b(op\.execute|text)\s*\(\s*[rbuf]*['\"]{1,3}\s*(DELETE|TRUNCATE|DROP)\b", re.I),
}


@dataclass
class Pending:
    revision: str
    description: str
    destructive: list[str]


def destructive_reasons(upgrade_source: str) -> list[str]:
    return [reason for reason, pattern in DESTRUCTIVE_PATTERNS.items() if pattern.search(upgrade_source)]


def pending_migrations() -> tuple[str | None, list[Pending]]:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.core.config import BASE_DIR
    from app.core.database import engine

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    out: list[Pending] = []
    # walk_revisions goes newest -> oldest; stop at the database's current revision.
    for rev in script.walk_revisions("base", "heads"):
        if current is not None and rev.revision == current:
            break
        source = inspect.getsource(rev.module.upgrade) if hasattr(rev.module, "upgrade") else ""
        out.append(Pending(rev.revision, (rev.doc or "").strip().splitlines()[0] if rev.doc else "", destructive_reasons(source)))
    out.reverse()
    return current, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    try:
        current, pending = pending_migrations()
    except Exception as exc:  # reported, never hidden: deploy.sh stops on exit code 1
        print(f"Could not check migrations: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    risky = [p for p in pending if p.destructive]
    if args.json:
        print(json.dumps({"current": current, "pending": [asdict(p) for p in pending], "destructive": bool(risky)}))
    elif not pending:
        print(f"Database is up to date (revision {current}).")
    else:
        print(f"{len(pending)} migration(s) to apply (database is at {current or 'empty'}):")
        for p in pending:
            flag = f"   <-- {', '.join(p.destructive)}" if p.destructive else ""
            print(f"  {p.revision}  {p.description}{flag}")
        if risky:
            print("\nAt least one migration removes or rewrites data. A verified backup is taken first; confirm only "
                  "after reading those migrations.")
    return 3 if risky else 0


if __name__ == "__main__":
    raise SystemExit(main())
