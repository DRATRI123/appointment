"""Password hashing (Argon2id) and policy."""
from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.exceptions import ValidationFailed

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        # Run a dummy verification so timing does not reveal whether the account has a password.
        try:
            _hasher.verify(_hasher.hash("dummy-password"), "not-it")
        except VerificationError:
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_policy(password: str) -> None:
    if len(password) < 8:
        raise ValidationFailed("Password must be at least 8 characters long.", code="weak_password")
    if len(password) > 128:
        raise ValidationFailed("Password is too long.", code="weak_password")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationFailed("Password must contain letters and numbers.", code="weak_password")
