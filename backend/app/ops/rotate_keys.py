"""Re-encrypt every protected field with the current DATA_ENCRYPTION_KEY: ``python -m app.ops.rotate_keys``.

Rotating the key (docs/security.md):
  1. Back up (``python -m app.ops.backup create``) and keep the old key.
  2. Set DATA_ENCRYPTION_KEY to a new key and put the old one in DATA_ENCRYPTION_PREVIOUS_KEYS; restart the API and
     worker. Everything keeps working: old values are read with the old key, new values use the new key.
  3. Run this command. It also encrypts any value still stored as plain text from before encryption existed.
  4. When it reports nothing left, remove the old key from DATA_ENCRYPTION_PREVIOUS_KEYS and restart.

``--dry-run`` only counts. Values that cannot be decrypted are reported and left untouched; the command then exits 1.
It works in batches with a commit after each, so it can be stopped and run again safely.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.database import session_scope
from app.models import CustomerNote, IdempotencyKey, Integration, MessagingProviderConfig, User, WebhookEndpoint
from app.security.crypto import DecryptionError, current_key_id, decrypt_text, encrypt_text, needs_reencryption

FIELDS = [
    (CustomerNote, "body_encrypted"),
    (Integration, "credentials_encrypted"),
    (MessagingProviderConfig, "secrets_encrypted"),
    (WebhookEndpoint, "secret_encrypted"),
    (User, "mfa_secret"),
    (IdempotencyKey, "response_body"),
]
BATCH = 500


def rotate(*, dry_run: bool = False) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    for model, column in FIELDS:
        name = f"{model.__tablename__}.{column}"
        counts = {"checked": 0, "reencrypted": 0, "failed": 0}
        last_id = 0
        while True:
            with session_scope() as db:
                rows = db.scalars(select(model).where(model.id > last_id, getattr(model, column).is_not(None)).order_by(model.id).limit(BATCH)).all()
                if not rows:
                    break
                for row in rows:
                    last_id = row.id
                    counts["checked"] += 1
                    value = getattr(row, column)
                    if not needs_reencryption(value):
                        continue
                    try:
                        plain = decrypt_text(value)
                    except DecryptionError:
                        counts["failed"] += 1
                        continue
                    counts["reencrypted"] += 1
                    if not dry_run:
                        setattr(row, column, encrypt_text(plain))
        report[name] = counts
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="count what would change, change nothing")
    args = parser.parse_args()
    report = rotate(dry_run=args.dry_run)
    print(f"Current key id: {current_key_id()}{'  (dry run, nothing changed)' if args.dry_run else ''}")
    for name, c in report.items():
        print(f"  {name:40} checked {c['checked']:>6}  {'would re-encrypt' if args.dry_run else 're-encrypted'} {c['reencrypted']:>6}  failed {c['failed']:>4}")
    failed = sum(c["failed"] for c in report.values())
    if failed:
        print(f"{failed} value(s) could not be decrypted with any configured key. They were left unchanged.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
