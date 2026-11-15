"""Abuse limits, counted from the challenges table so every API process sees the same numbers.

On top of these, the public routes have per-IP request limits (slowapi) and each challenge has its own resend
cool-down and resend cap.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import RateLimited
from app.core.time import utcnow
from app.models.verification import OtpChallenge

# Hard ceiling per destination across all clinics, so one number cannot be flooded through many clinic pages.
GLOBAL_PER_DESTINATION_HOUR = 10


def _count(db: Session, *conditions) -> int:
    since = utcnow() - timedelta(hours=1)
    return db.scalar(select(func.count()).select_from(OtpChallenge).where(OtpChallenge.created_at >= since, *conditions)) or 0


def _sends(db: Session, *conditions) -> int:
    """Codes sent in the last hour, counting resends of each challenge."""
    since = utcnow() - timedelta(hours=1)
    return db.scalar(select(func.coalesce(func.sum(OtpChallenge.resend_count + 1), 0)).where(OtpChallenge.created_at >= since, *conditions)) or 0


def check_new_challenge(db: Session, *, organization_id: int, destination: str, ip: str | None, session_key: str, policy: dict) -> None:
    if _sends(db, OtpChallenge.organization_id == organization_id, OtpChallenge.destination == destination) >= policy["limit_per_destination_hour"]:
        raise RateLimited("Too many codes were sent to this number or address. Please try again in an hour.", code="otp_destination_limit")
    if _sends(db, OtpChallenge.destination == destination) >= GLOBAL_PER_DESTINATION_HOUR:
        raise RateLimited("Too many codes were sent to this number or address. Please try again in an hour.", code="otp_destination_limit")
    if ip and _count(db, OtpChallenge.organization_id == organization_id, OtpChallenge.ip_address == ip) >= policy["limit_per_ip_hour"]:
        raise RateLimited("Too many verification attempts from this network. Please try again later.", code="otp_ip_limit")
    if _count(db, OtpChallenge.organization_id == organization_id, OtpChallenge.session_key == session_key) >= policy["limit_per_session_hour"]:
        raise RateLimited("Too many codes requested for this booking. Please try again later.", code="otp_session_limit")


def check_cooldown(challenge: OtpChallenge, policy: dict) -> None:
    if challenge.last_sent_at is None:
        return
    wait = int((challenge.last_sent_at + timedelta(seconds=policy["resend_cooldown_seconds"]) - utcnow()).total_seconds())
    if wait > 0:
        raise RateLimited(f"Please wait {wait} seconds before asking for another code.", code="otp_cooldown", headers={"Retry-After": str(wait)})
