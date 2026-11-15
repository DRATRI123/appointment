"""Checking a submitted code. Wrong attempts are saved even though the request fails (``persist=True``)."""
from __future__ import annotations

from app.core.exceptions import AuthenticationError, ConflictError, RateLimited
from app.core.time import utcnow
from app.models.verification import OtpChallenge
from app.services.otp.otp_generator import matches


def verify(challenge: OtpChallenge, code: str) -> None:
    now = utcnow()
    if challenge.verified_at is not None:
        raise ConflictError("This code was already used. Request a new one if you need to verify again.", code="otp_used")
    if challenge.invalidated_at is not None:
        raise AuthenticationError("A newer code was sent. Please use the latest one.", code="otp_superseded")
    if challenge.delivery_status == "failed":
        raise AuthenticationError("This code could not be delivered. Please request a new one.", code="otp_not_delivered")
    if challenge.expires_at <= now:
        raise AuthenticationError("This code has expired. Request a new one.", code="otp_expired")
    if challenge.attempts >= challenge.max_attempts:
        raise RateLimited("Too many incorrect attempts. Request a new code.", code="otp_locked")
    if not code.isdigit() or not matches(challenge.public_id, challenge.destination, code, challenge.code_hash):
        challenge.attempts += 1
        remaining = challenge.max_attempts - challenge.attempts
        if remaining <= 0:
            raise RateLimited("Too many incorrect attempts. Request a new code.", code="otp_locked", persist=True)
        raise AuthenticationError(f"That code is not right. {remaining} attempt{'s' if remaining != 1 else ''} left.", code="otp_incorrect", persist=True)
    challenge.verified_at = now
