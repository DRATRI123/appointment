"""Field encryption: key ids, reading data written with an older key or the old format, and re-encryption."""
from __future__ import annotations

import base64
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.security import crypto


def _key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture()
def keys(monkeypatch):
    settings = get_settings()

    def use(current: str, *previous: str) -> None:
        monkeypatch.setattr(settings, "data_encryption_key", current)
        monkeypatch.setattr(settings, "data_encryption_previous_keys", list(previous))

    return use


def test_new_values_carry_the_key_id_and_a_fresh_nonce(keys):
    keys(_key())
    a, b = crypto.encrypt_text("same text"), crypto.encrypt_text("same text")
    assert a.startswith(f"enc:v2:{crypto.current_key_id()}:") and a != b
    assert crypto.decrypt_text(a) == crypto.decrypt_text(b) == "same text"


def test_after_rotation_old_values_still_read_and_are_flagged(keys):
    old, new = _key(), _key()
    keys(old)
    before = crypto.encrypt_text("clinical note")
    keys(new, old)
    assert crypto.decrypt_text(before) == "clinical note"
    assert crypto.needs_reencryption(before)
    after = crypto.encrypt_text("clinical note")
    assert not crypto.needs_reencryption(after)
    keys(new)  # old key removed too early: a clear error, never garbage or plain text
    with pytest.raises(crypto.DecryptionError, match="DATA_ENCRYPTION_PREVIOUS_KEYS"):
        crypto.decrypt_text(before)


def test_the_original_v1_format_is_still_readable(keys):
    k = _key()
    keys(k)
    nonce = os.urandom(12)
    v1 = "enc:v1:" + base64.urlsafe_b64encode(nonce + AESGCM(base64.b64decode(k)).encrypt(nonce, b"legacy", None)).decode()
    assert crypto.decrypt_text(v1) == "legacy" and crypto.needs_reencryption(v1)


def test_tampering_is_detected(keys):
    keys(_key())
    token = crypto.encrypt_text("secret")
    kid = token.split(":")[2]
    forged = token.replace(f":{kid}:", ":00000000:")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_text(forged)
    raw = bytearray(base64.urlsafe_b64decode(token.split(":", 3)[3]))
    raw[-1] ^= 1
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_text(token.rsplit(":", 1)[0] + ":" + base64.urlsafe_b64encode(bytes(raw)).decode())


def test_production_never_falls_back_to_plain_text(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "data_encryption_key", "")
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
        crypto.encrypt_text("x")


def test_rotate_command_reencrypts_everything(db, keys, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy import select

    from app.models import User
    from app.ops import rotate_keys

    old, new = _key(), _key()
    keys(old)
    user = db.scalar(select(User).limit(1)) or User(full_name="Rotation Test", email="rot@example.com")
    db.add(user)
    user.mfa_secret = crypto.encrypt_text("JBSWY3DPEHPK3PXP")
    db.flush()

    @contextmanager
    def same_session():
        yield db
        db.flush()

    monkeypatch.setattr(rotate_keys, "session_scope", same_session)
    keys(new, old)
    dry = rotate_keys.rotate(dry_run=True)
    assert dry["users.mfa_secret"]["reencrypted"] >= 1
    report = rotate_keys.rotate()
    assert report["users.mfa_secret"]["reencrypted"] >= 1 and report["users.mfa_secret"]["failed"] == 0
    assert not crypto.needs_reencryption(user.mfa_secret)
    keys(new)  # old key can now be removed
    assert crypto.decrypt_text(user.mfa_secret) == "JBSWY3DPEHPK3PXP"
