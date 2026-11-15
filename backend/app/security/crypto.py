"""Application-level field encryption (AES-256-GCM) for sensitive values: clinical notes, integration and messaging
credentials, webhook secrets, two-step sign-in secrets and stored idempotent responses.

Keys
* ``DATA_ENCRYPTION_KEY`` (base64 of 32 random bytes) encrypts everything new.
* ``DATA_ENCRYPTION_PREVIOUS_KEYS`` (comma-separated, optional) only decrypt older data after a key rotation.
* In development/test a key is derived from ``SECRET_KEY`` so the app runs without extra setup. Production refuses to
  start without an explicit key (app.core.config), so it can be rotated independently of session signing.

Format: ``enc:v2:<key id>:<base64(nonce | ciphertext+tag)>``. The key id (8 hex characters of SHA-256 of the key) says
which key to use and is bound to the ciphertext as associated data. Every value gets a fresh random 96-bit nonce.
``enc:v1:<...>`` values (before key ids existed) are still read, trying the current key and then the previous ones.
``python -m app.ops.rotate_keys`` re-encrypts everything with the current key.

Encryption never falls back to storing plain text: a missing or invalid key is an error.
"""
from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

PREFIX_V1 = "enc:v1:"
PREFIX_V2 = "enc:v2:"
PREFIX = PREFIX_V2  # what new values start with


class DecryptionError(RuntimeError):
    """The value cannot be decrypted with any configured key (wrong or missing key, or tampered data)."""


def _decode_key(value: str, name: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be base64.") from exc
    if len(raw) != 32:
        raise RuntimeError(f"{name} must decode to 32 bytes.")
    return raw


def key_id(key: bytes) -> str:
    return hashlib.sha256(b"field-key:" + key).hexdigest()[:8]


@lru_cache(maxsize=4)
def _ring(current: str, previous: tuple[str, ...], secret_key: str, app_env: str) -> tuple[bytes, dict[str, bytes]]:
    if current:
        primary = _decode_key(current, "DATA_ENCRYPTION_KEY")
    elif app_env in {"development", "test"}:
        primary = hashlib.sha256(f"field-encryption:{secret_key}".encode()).digest()
    else:
        raise RuntimeError("DATA_ENCRYPTION_KEY is required outside development.")
    keys = [primary] + [_decode_key(k, "DATA_ENCRYPTION_PREVIOUS_KEYS") for k in previous]
    return primary, {key_id(k): k for k in keys}


def _keys() -> tuple[bytes, dict[str, bytes]]:
    s = get_settings()
    return _ring(s.data_encryption_key, tuple(s.data_encryption_previous_keys), s.secret_key, s.app_env)


def current_key_id() -> str:
    return key_id(_keys()[0])


def encrypt_text(plaintext: str) -> str:
    primary, _ = _keys()
    kid = key_id(primary)
    nonce = os.urandom(12)
    ciphertext = AESGCM(primary).encrypt(nonce, plaintext.encode("utf-8"), f"{PREFIX_V2}{kid}".encode())
    return f"{PREFIX_V2}{kid}:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(token: str) -> str:
    if token.startswith(PREFIX_V2):
        kid, _, body = token[len(PREFIX_V2):].partition(":")
        key = _keys()[1].get(kid)
        if key is None:
            raise DecryptionError(f"No configured key with id {kid}. Add the old key to DATA_ENCRYPTION_PREVIOUS_KEYS.")
        raw = base64.urlsafe_b64decode(body)
        try:
            return AESGCM(key).decrypt(raw[:12], raw[12:], f"{PREFIX_V2}{kid}".encode()).decode("utf-8")
        except InvalidTag as exc:
            raise DecryptionError("Encrypted value was modified or the key is wrong.") from exc
    if token.startswith(PREFIX_V1):
        raw = base64.urlsafe_b64decode(token[len(PREFIX_V1):])
        for key in _keys()[1].values():
            try:
                return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode("utf-8")
            except InvalidTag:
                continue
        raise DecryptionError("Encrypted value could not be decrypted with the current or previous keys.")
    # Rows written before encryption existed. Read as they are; ``python -m app.ops.rotate_keys`` encrypts them.
    return token


def is_encrypted(value: str | None) -> bool:
    return bool(value and (value.startswith(PREFIX_V2) or value.startswith(PREFIX_V1)))


def needs_reencryption(value: str | None) -> bool:
    """Plain text, the old format, or encrypted with a key other than the current one."""
    if not value:
        return False
    if not value.startswith(PREFIX_V2):
        return True
    return value[len(PREFIX_V2):].partition(":")[0] != current_key_id()
