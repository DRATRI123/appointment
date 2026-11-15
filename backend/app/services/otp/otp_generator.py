"""Codes and their hashes. The plain code exists only in memory between generation and delivery."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import get_settings


def generate_code(length: int) -> str:
    if length not in (4, 6, 8):
        raise ValueError("OTP length must be 4, 6 or 8 digits")
    s = get_settings()
    if s.otp_test_code and s.app_env in {"development", "test"} and len(s.otp_test_code) == length and s.otp_test_code.isdigit():
        return s.otp_test_code  # local load tests only; refused at start-up anywhere else
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_code(challenge_id: str, destination: str, code: str) -> str:
    """HMAC with the server pepper, bound to the challenge and destination: a hash copied to another row is useless."""
    s = get_settings()
    key = (s.otp_pepper or s.secret_key).encode()
    return hmac.new(key, f"otp:{challenge_id}:{destination}:{code}".encode(), hashlib.sha256).hexdigest()


def matches(challenge_id: str, destination: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(challenge_id, destination, code), code_hash)
