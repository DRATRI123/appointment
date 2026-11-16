"""A column type that is encrypted in the database and plain in Python (AES-256-GCM, app.security.crypto).

Use it for sensitive values the app never searches or sorts on (e.g. a payer's UPI id, notes about a family member).
Values written before the column was encrypted are read as they are; ``python -m app.ops.rotate_keys`` encrypts them.
"""
from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        from app.security.crypto import encrypt_text, is_encrypted

        return value if is_encrypted(value) else encrypt_text(str(value))

    def process_result_value(self, value, dialect):
        if not value:
            return value
        from app.security.crypto import decrypt_text

        return decrypt_text(value)
