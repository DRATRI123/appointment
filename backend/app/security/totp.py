"""Time-based one-time passwords (RFC 6238) for two-step sign-in with an authenticator app.

Standard parameters every authenticator app supports: SHA-1, 6 digits, 30-second steps. A code is accepted for the
current step and one step either side (clock drift), and never twice: the last accepted step is stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
DRIFT_STEPS = 1


def new_secret() -> str:
    """160 random bits, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()  # nosec B324 - RFC 6238 mandates HMAC-SHA1
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD)


def code_at(secret: str, now: float | None = None) -> str:
    return _code(secret, current_step(now))


def verify(secret: str, code: str, *, last_step: int | None, now: float | None = None) -> int | None:
    """The step the code belongs to if it is valid and newer than ``last_step``, else None."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if last_step is not None and candidate <= last_step:
            continue  # already used: a code seen over someone's shoulder cannot be replayed
        if hmac.compare_digest(_code(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"


def new_recovery_codes(count: int = 10) -> list[str]:
    """Single-use backup codes like ``7KQ4-M2XD``: 40 bits each, no ambiguous characters."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(count)]


def hash_recovery_code(code: str, pepper: str) -> str:
    normalized = "".join(ch for ch in code.upper() if ch.isalnum())
    return hmac.new(pepper.encode(), f"mfa-recovery:{normalized}".encode(), hashlib.sha256).hexdigest()
