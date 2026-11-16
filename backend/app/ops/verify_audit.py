"""Check that no audit record was changed: ``python -m app.ops.verify_audit [--since 2026-11-01]``

Every audit row carries an HMAC of its content made with a key derived from DATA_ENCRYPTION_KEY (purpose "audit").
Someone who can edit the database but does not have the server's key cannot alter a row, or insert a fake one,
without this command reporting it. On PostgreSQL a trigger also refuses UPDATE and DELETE on audit_logs outright.

Exit codes: 0 all signed rows match; 1 at least one row was altered (listed); rows from before signing existed are
counted as "unsigned" and do not fail the check. After a key rotation, rows signed with the old key are reported as
altered until the old key is removed from verification: run this before rotating, keep its output.
"""
from __future__ import annotations

import argparse
import hmac
import sys
from datetime import date, datetime, time

from sqlalchemy import select

from app.core.database import session_scope
from app.models import AuditLog
from app.services.audit_service import sign_audit_row

BATCH = 1000


def verify(since: date | None = None) -> dict:
    counts = {"checked": 0, "unsigned": 0, "altered": 0}
    altered: list[str] = []
    last_id = 0
    while True:
        with session_scope() as db:
            q = select(AuditLog).where(AuditLog.id > last_id).order_by(AuditLog.id).limit(BATCH)
            if since:
                q = q.where(AuditLog.created_at >= datetime.combine(since, time.min))
            rows = db.scalars(q).all()
            if not rows:
                break
            for row in rows:
                last_id = row.id
                counts["checked"] += 1
                if not row.signature:
                    counts["unsigned"] += 1
                elif not hmac.compare_digest(row.signature, sign_audit_row(row)):
                    counts["altered"] += 1
                    altered.append(f"{row.public_id} {row.created_at.isoformat()} {row.action}")
    counts["altered_rows"] = altered
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=date.fromisoformat, help="only rows from this date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    result = verify(args.since)
    print(f"Checked {result['checked']} audit rows: {result['altered']} altered, {result['unsigned']} from before signing.")
    for line in result["altered_rows"][:50]:
        print("  ALTERED:", line)
    return 1 if result["altered"] else 0


if __name__ == "__main__":
    sys.exit(main())
