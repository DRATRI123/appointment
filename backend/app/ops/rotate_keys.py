"""Re-encrypt every protected field with the current DATA_ENCRYPTION_KEY: ``python -m app.ops.rotate_keys``.

Rotating the key (docs/security.md):
  1. Back up (``python -m app.ops.backup create``) and keep the old key.
  2. Set DATA_ENCRYPTION_KEY to a new key and put the old one in DATA_ENCRYPTION_PREVIOUS_KEYS; restart the API and
     worker. Everything keeps working: old values are read with the old key, new values use the new key.
  3. Run this command. It also encrypts any value still stored as plain text from before encryption existed.
  4. When it reports nothing left, remove the old key from DATA_ENCRYPTION_PREVIOUS_KEYS and restart.

Covers: encrypted columns (clinical notes, credentials, provider secrets, webhook secrets, two-step secrets, stored
responses, family-member notes, payer UPI id and name), answers to sensitive booking-form fields, and every private
uploaded file (patient documents, payment screenshots, refund proofs, form attachments).

``--dry-run`` only counts. Values that cannot be decrypted are reported and left untouched; the command then exits 1.
It works in batches with a commit after each, so it can be stopped and run again safely.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import Text, cast, select, update

from app.core.database import session_scope
from app.models import (
    BookingFormField,
    BookingFormResponse,
    CustomerDependent,
    CustomerNote,
    IdempotencyKey,
    Integration,
    MessagingProviderConfig,
    PaymentSubmission,
    User,
    WebhookEndpoint,
)
from app.security.crypto import DecryptionError, current_key_id, decrypt_text, encrypt_text, needs_reencryption

FIELDS = [
    (CustomerNote, "body_encrypted"),
    (Integration, "credentials_encrypted"),
    (MessagingProviderConfig, "secrets_encrypted"),
    (WebhookEndpoint, "secret_encrypted"),
    (User, "mfa_secret"),
    (IdempotencyKey, "response_body"),
    (CustomerDependent, "notes"),
    (PaymentSubmission, "payer_upi_id"),
    (PaymentSubmission, "payer_name"),
]
BATCH = 500


def _new_counts() -> dict[str, int]:
    return {"checked": 0, "reencrypted": 0, "failed": 0}


def _rotate_columns(dry_run: bool, report: dict[str, dict[str, int]]) -> None:
    """Works on the stored text itself (cast to TEXT), so columns that decrypt automatically are handled too."""
    for model, column in FIELDS:
        table = model.__table__
        col = table.c[column]
        name = f"{table.name}.{column}"
        counts = _new_counts()
        last_id = 0
        while True:
            with session_scope() as db:
                rows = db.execute(select(table.c.id, cast(col, Text)).where(table.c.id > last_id, col.is_not(None))
                                  .order_by(table.c.id).limit(BATCH)).all()
                if not rows:
                    break
                for row_id, value in rows:
                    last_id = row_id
                    counts["checked"] += 1
                    if not value or not needs_reencryption(value):
                        continue
                    try:
                        plain = decrypt_text(value)
                    except DecryptionError:
                        counts["failed"] += 1
                        continue
                    counts["reencrypted"] += 1
                    if not dry_run:
                        db.execute(update(table).where(table.c.id == row_id).values({column: encrypt_text(plain)}))
                db.expire_all()  # direct UPDATEs: objects already loaded in this session must not keep the old text
        report[name] = counts


def _rotate_form_answers(dry_run: bool, report: dict[str, dict[str, int]]) -> None:
    """Answers to sensitive booking-form fields: encrypt plain ones (written before encryption existed), re-key old ones."""
    import json

    counts = _new_counts()
    last_id = 0
    while True:
        with session_scope() as db:
            rows = db.scalars(select(BookingFormResponse).where(BookingFormResponse.id > last_id).order_by(BookingFormResponse.id).limit(BATCH)).all()
            if not rows:
                break
            sensitive: dict[int, set[str]] = {}
            for fid in {r.form_id for r in rows}:
                sensitive[fid] = set(db.scalars(select(BookingFormField.key).where(BookingFormField.form_id == fid, BookingFormField.is_sensitive.is_(True))))
            for row in rows:
                last_id = row.id
                counts["checked"] += 1
                answers, changed = dict(row.answers or {}), False
                for key, value in list(answers.items()):
                    sealed = isinstance(value, dict) and set(value) == {"enc"}
                    if sealed and needs_reencryption(value["enc"]):
                        try:
                            answers[key] = {"enc": encrypt_text(decrypt_text(value["enc"]))}
                        except DecryptionError:
                            counts["failed"] += 1
                            continue
                        changed = True
                    elif not sealed and key in sensitive.get(row.form_id, set()) and value not in (None, "", []):
                        answers[key] = {"enc": encrypt_text(json.dumps(value))}
                        changed = True
                if changed:
                    counts["reencrypted"] += 1
                    if not dry_run:
                        row.answers = answers
    report["booking_form_responses.answers (sensitive fields)"] = counts


def _rotate_files(dry_run: bool, report: dict[str, dict[str, int]]) -> None:
    """Private uploaded files: encrypt plain ones, re-encrypt those under an older key. Rewritten in place."""
    from app.core.storage import EncryptingStorage, get_storage
    from app.security.crypto import blob_needs_reencryption, decrypt_bytes, encrypt_bytes, is_encrypted_blob

    storage = get_storage()
    counts = _new_counts()
    if not isinstance(storage, EncryptingStorage):
        report["private files"] = counts
        return
    for key in storage.private_keys():
        counts["checked"] += 1
        raw = storage.read_raw(key)
        if is_encrypted_blob(raw) and not blob_needs_reencryption(raw):
            continue
        try:
            plain = decrypt_bytes(raw)
        except DecryptionError:
            counts["failed"] += 1
            continue
        counts["reencrypted"] += 1
        if not dry_run:
            storage.write_raw(key, encrypt_bytes(plain))
    report["private files"] = counts


def rotate(*, dry_run: bool = False, files: bool = True) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    _rotate_columns(dry_run, report)
    _rotate_form_answers(dry_run, report)
    if files:
        _rotate_files(dry_run, report)
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
