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


# --- Files and purpose-separated keys ------------------------------------------------------------------------------
# Private files (patient documents, payment screenshots, refund proofs, form attachments) are encrypted with a key
# DERIVED from each DATA_ENCRYPTION_KEY for that purpose only (HKDF-SHA256, info="purpose:files"): a key leaked from
# one purpose cannot decrypt another, and rotating DATA_ENCRYPTION_KEY rotates every purpose key with it.
# File format: b"APENC1" | key id (8 ascii) | nonce (12) | ciphertext+tag. Files written before encryption existed are
# read as they are; ``python -m app.ops.rotate_keys`` encrypts them.
FILE_MAGIC = b"APENC1"


@lru_cache(maxsize=32)
def purpose_key(key: bytes, purpose: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"appointment-platform", info=f"purpose:{purpose}".encode()).derive(key)


def encrypt_bytes(data: bytes, purpose: str = "files") -> bytes:
    primary, _ = _keys()
    kid = key_id(primary)
    nonce = os.urandom(12)
    header = FILE_MAGIC + kid.encode("ascii")
    return header + nonce + AESGCM(purpose_key(primary, purpose)).encrypt(nonce, data, header + purpose.encode())


def is_encrypted_blob(data: bytes) -> bool:
    return data[: len(FILE_MAGIC)] == FILE_MAGIC


def blob_key_id(data: bytes) -> str | None:
    return data[len(FILE_MAGIC): len(FILE_MAGIC) + 8].decode("ascii") if is_encrypted_blob(data) else None


def decrypt_bytes(data: bytes, purpose: str = "files") -> bytes:
    if not is_encrypted_blob(data):
        return data  # written before file encryption existed
    kid = blob_key_id(data) or ""
    key = _keys()[1].get(kid)
    if key is None:
        raise DecryptionError(f"No configured key with id {kid}. Add the old key to DATA_ENCRYPTION_PREVIOUS_KEYS.")
    header = data[: len(FILE_MAGIC) + 8]
    body = data[len(header):]
    try:
        return AESGCM(purpose_key(key, purpose)).decrypt(body[:12], body[12:], header + purpose.encode())
    except InvalidTag as exc:
        raise DecryptionError("Encrypted file was modified or the key is wrong.") from exc


def blob_needs_reencryption(data: bytes) -> bool:
    return blob_key_id(data) != current_key_id()


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 with a purpose key: for tamper-evident audit rows and signed download links (not reversible)."""
    import hmac

    return hmac.new(purpose_key(_keys()[0], purpose), value.encode("utf-8"), hashlib.sha256).hexdigest()
