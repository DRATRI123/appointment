"""Application-level field encryption (AES-256-GCM) for sensitive text such as clinical notes.

Key: ``DATA_ENCRYPTION_KEY`` (base64, 32 bytes). In development/test a key is derived from
``SECRET_KEY`` so the app runs without extra setup; production must set an explicit key so it can be
rotated independently of session signing.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

PREFIX = "enc:v1:"


def _key() -> bytes:
    settings = get_settings()
    if settings.data_encryption_key:
        raw = base64.b64decode(settings.data_encryption_key)
        if len(raw) != 32:
            raise RuntimeError("DATA_ENCRYPTION_KEY must decode to 32 bytes.")
        return raw
    if settings.app_env not in {"development", "test"}:
        raise RuntimeError("DATA_ENCRYPTION_KEY is required outside development.")
    return hashlib.sha256(f"field-encryption:{settings.secret_key}".encode()).digest()


def encrypt_text(plaintext: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(token: str) -> str:
    if not token.startswith(PREFIX):
        return token  # legacy/plain value
    raw = base64.urlsafe_b64decode(token[len(PREFIX):])
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(PREFIX))
