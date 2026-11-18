"""Start, resend and verify one-time codes for public bookings, and check the resulting token at booking time.

The same clinic channels (its own SMS / WhatsApp / email account, the platform's as fallback), limits, expiry and audit
also sign patients in on the clinic's website (``start_sign_in`` / ``verify_sign_in``, purpose ``patient_login``): they
see their bookings without a password and without keeping each booking's link.

A challenge belongs to one clinic, one browser session (``session_key``) and one held slot. Verifying it returns a
signed token naming the channel and the exact destination (mobile number or email). The booking API accepts the
booking only if the customer's own contact details for that channel are the verified destination, so nobody can
verify their own number and book with someone else's, and calling the booking API directly without a token fails.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import HoldStatus
from app.core.exceptions import AppError, NotFoundError, PermissionDenied, RateLimited, SlotUnavailable, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models import BookingHold, Organization, User
from app.models.verification import OtpChallenge
from app.security.identifiers import normalize_mobile
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService
from app.services.otp import email_provider, otp_rate_limiter, otp_verifier, sms_provider, whatsapp_provider
from app.services.otp.channels import sender_for
from app.services.otp.otp_generator import generate_code, hash_code

log = get_logger(__name__)

# JWT "typ" claim for the booking token (bandit mistakes the name for a password).
TOKEN_TYPE = "booking_contact"  # nosec B105
TOKEN_MINUTES = 30
SENDERS = {"sms": sms_provider.send_otp, "whatsapp": whatsapp_provider.send_otp, "email": email_provider.send_otp}
CHANNEL_NAMES = {"sms": "SMS", "whatsapp": "WhatsApp", "email": "email"}
BOOKING = "booking"
SIGN_IN = "patient_login"


class OTPDeliveryFailed(AppError):
    status_code = 503
    code = "otp_delivery_failed"


def load_policy(db: Session, org: Organization) -> dict[str, Any]:
    settings = OrganizationService(db).get_settings(org)
    policy = dict(settings.get("otp", {}))
    # Older switch from the booking settings: turning it off still turns verification off.
    if settings.get("booking", {}).get("require_mobile_verification") is False:
        policy["required_for_booking"] = False
    return policy


def booking_verification_required(db: Session, org: Organization) -> bool:
    p = load_policy(db, org)
    return bool(p.get("enabled", True) and p.get("required_for_booking", True))


def available_channels(db: Session, org: Organization, policy: dict[str, Any] | None = None) -> list[str]:
    """Channels the clinic enabled *and* can actually deliver (its own account or the platform's)."""
    policy = policy or load_policy(db, org)
    return [c for c in policy.get("channels", ["sms"]) if sender_for(db, org.id, c) is not None]


def normalize_destination(channel: str, raw: str | None) -> str:
    value = (raw or "").strip()
    if channel == "email":
        import re

        value = value.lower()
        if not re.fullmatch(r"[^@\s<>\"']{1,64}@[a-z0-9.-]+\.[a-z]{2,}", value) or len(value) > 254:
            raise ValidationFailed("Enter a valid email address.", code="invalid_email")
        return value
    if not value:
        raise ValidationFailed("Enter your mobile number.", code="mobile_required")
    return normalize_mobile(value)


def mask(channel: str, destination: str) -> str:
    if channel == "email":
        name, _, domain = destination.partition("@")
        return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"
    return f"{destination[:3]}•••••{destination[-3:]}"


class OTPService:
    def __init__(self, db: Session, org: Organization, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.meta = meta or RequestMeta()
        self.policy = load_policy(db, org)

    # ------------------------------------------------------------------------------------------- helpers
    def _hold(self, hold_id: str, session_key: str) -> BookingHold:
        hold = self.db.scalar(select(BookingHold).where(BookingHold.public_id == hold_id, BookingHold.organization_id == self.org.id))
        if hold is None:
            raise ValidationFailed("Choose a time first.", code="hold_not_found")
        if hold.session_key != session_key:
            raise PermissionDenied("This reservation belongs to another browser session.", code="hold_mismatch")
        if hold.status != HoldStatus.ACTIVE or hold.expires_at <= utcnow():
            raise SlotUnavailable("Your reserved time has expired. Please choose the time again.", code="hold_expired")
        return hold

    def _challenge(self, challenge_id: str, session_key: str) -> OtpChallenge:
        ch = self.db.scalar(select(OtpChallenge).where(OtpChallenge.public_id == challenge_id, OtpChallenge.organization_id == self.org.id))
        # Same answer for "unknown" and "someone else's": nothing to learn by guessing ids.
        if ch is None or ch.session_key != session_key:
            raise NotFoundError("This verification request was not found. Please request a new code.", code="otp_not_found")
        return ch

    def _deliver(self, ch: OtpChallenge, code: str) -> None:
        sender = sender_for(self.db, self.org.id, ch.channel)
        if sender is None:
            ch.delivery_status, ch.delivery_error = "failed", "channel not configured"
            raise OTPDeliveryFailed(f"Verification by {CHANNEL_NAMES[ch.channel]} is not available right now. Please choose another method.", persist=True)
        minutes = max(1, self.policy["expiry_seconds"] // 60)
        try:
            result = SENDERS[ch.channel](sender, destination=ch.destination, code=code, minutes=minutes, clinic=self.org.name)
        except Exception as exc:  # a provider bug must not leak details or the code
            log.warning("otp.provider_error", channel=ch.channel, error=type(exc).__name__)
            result = None
        ch.provider = sender.provider.name
        ch.last_sent_at = utcnow()
        if result is None or not result.ok:
            error = ((result.error if result else "provider error") or "").replace(code, "••••")[:300]
            ch.delivery_status, ch.delivery_error = "failed", error
            log.warning("otp.delivery_failed", channel=ch.channel, provider=ch.provider, source=sender.source, error=error)
            record_audit(self.db, action="booking.otp_delivery_failed", actor=None, organization_id=self.org.id, entity_type="otp_challenge",
                         entity_id=ch.public_id, after={"channel": ch.channel, "provider": ch.provider, "error": error}, meta=self.meta)
            raise OTPDeliveryFailed(f"We couldn't send the code by {CHANNEL_NAMES[ch.channel]}. Please try again or choose another method.", persist=True)
        ch.delivery_status, ch.delivery_error = "sent", None
        ch.provider_message_id = (result.message_id or "")[:160] or None

    def _issue(self, ch: OtpChallenge) -> str:
        code = generate_code(self.policy["code_length"])
        ch.code_hash = hash_code(ch.public_id, ch.destination, code)
        ch.expires_at = utcnow() + timedelta(seconds=self.policy["expiry_seconds"])
        ch.attempts = 0
        return code

    def describe(self, ch: OtpChallenge) -> dict[str, Any]:
        wait = 0
        if ch.last_sent_at:
            wait = max(0, int((ch.last_sent_at + timedelta(seconds=self.policy["resend_cooldown_seconds"]) - utcnow()).total_seconds()))
        return {
            "challenge_id": ch.public_id, "channel": ch.channel, "destination": mask(ch.channel, ch.destination),
            "code_length": self.policy["code_length"], "expires_in_seconds": max(0, int((ch.expires_at - utcnow()).total_seconds())),
            "resend_after_seconds": wait, "resends_left": max(0, self.policy["max_resends"] - ch.resend_count),
        }

    # ------------------------------------------------------------------------------------------- public steps
    def start(self, *, channel: str, destination: str, hold_id: str, session_key: str) -> dict[str, Any]:
        if not self.policy.get("enabled", True):
            raise ValidationFailed("Verification is switched off for this clinic.", code="otp_disabled")
        if channel not in available_channels(self.db, self.org, self.policy):
            raise ValidationFailed(f"Verification by {CHANNEL_NAMES.get(channel, channel)} is not available. Please choose another method.", code="otp_channel_unavailable")
        number = normalize_destination(channel, destination)
        hold = self._hold(hold_id, session_key)
        otp_rate_limiter.check_new_challenge(self.db, organization_id=self.org.id, destination=number, ip=self.meta.ip_address, session_key=session_key, policy=self.policy)
        now = utcnow()
        # A new request replaces every open code for this booking session.
        self.db.execute(update(OtpChallenge).where(
            OtpChallenge.organization_id == self.org.id, OtpChallenge.session_key == session_key, OtpChallenge.purpose == "booking",
            OtpChallenge.verified_at.is_(None), OtpChallenge.invalidated_at.is_(None)).values(invalidated_at=now))
        ch = OtpChallenge(organization_id=self.org.id, purpose="booking", channel=channel, destination=number, code_hash="-", max_attempts=self.policy["max_attempts"],
                          expires_at=now, session_key=session_key, hold_public_id=hold.public_id, ip_address=self.meta.ip_address)
        self.db.add(ch)
        self.db.flush()
        code = self._issue(ch)
        self._deliver(ch, code)
        record_audit(self.db, action="booking.otp_sent", actor=None, organization_id=self.org.id, entity_type="otp_challenge", entity_id=ch.public_id,
                     after={"channel": channel, "destination": mask(channel, number), "provider": ch.provider}, meta=self.meta)
        self.db.flush()
        return self.describe(ch)

    def resend(self, challenge_id: str, session_key: str) -> dict[str, Any]:
        ch = self._challenge(challenge_id, session_key)
        if ch.verified_at is not None or ch.invalidated_at is not None:
            raise ValidationFailed("This request is finished. Start again to get a new code.", code="otp_closed")
        if ch.purpose == BOOKING:
            self._hold(ch.hold_public_id or "", session_key)
        if ch.resend_count >= self.policy["max_resends"]:
            raise RateLimited("You have asked for the maximum number of codes. Try another method or try again later.", code="otp_resend_limit")
        otp_rate_limiter.check_cooldown(ch, self.policy)
        otp_rate_limiter.check_new_challenge(self.db, organization_id=self.org.id, destination=ch.destination, ip=self.meta.ip_address, session_key=session_key,
                                             policy={**self.policy, "limit_per_session_hour": 10**6})
        ch.resend_count += 1
        code = self._issue(ch)
        self._deliver(ch, code)
        record_audit(self.db, action="booking.otp_resent" if ch.purpose == BOOKING else "patient.sign_in_code_resent", actor=None, organization_id=self.org.id, entity_type="otp_challenge", entity_id=ch.public_id,
                     after={"channel": ch.channel, "resend": ch.resend_count}, meta=self.meta)
        self.db.flush()
        return self.describe(ch)

    def verify(self, challenge_id: str, code: str, session_key: str) -> dict[str, Any]:
        ch = self._challenge(challenge_id, session_key)
        if ch.purpose != BOOKING:
            raise NotFoundError("This verification request was not found. Please request a new code.", code="otp_not_found")
        hold = self._hold(ch.hold_public_id or "", session_key)
        otp_verifier.verify(ch, code.strip())
        self.db.flush()
        now = utcnow()
        token = jwt.encode({
            "typ": TOKEN_TYPE, "org": self.org.public_id, "hold": hold.public_id, "sid": session_key, "ch": ch.channel, "dst": ch.destination,
            "cid": ch.public_id, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=TOKEN_MINUTES)).timestamp()),
        }, get_settings().secret_key, algorithm="HS256")
        record_audit(self.db, action="booking.otp_verified", actor=None, organization_id=self.org.id, entity_type="otp_challenge", entity_id=ch.public_id,
                     after={"channel": ch.channel}, meta=self.meta)
        return {"verification_token": token, "channel": ch.channel, "destination": ch.destination, "expires_in_seconds": TOKEN_MINUTES * 60}

    # ------------------------------------------------------------------------------------- patient sign-in
    def start_sign_in(self, *, channel: str, destination: str, session_key: str) -> dict[str, Any]:
        """A code to the patient's mobile number (SMS / WhatsApp) or email, through the clinic's channels."""
        if channel not in available_channels(self.db, self.org, self.policy):
            raise ValidationFailed(f"Sign-in by {CHANNEL_NAMES.get(channel, channel)} is not available. Please choose another method.", code="otp_channel_unavailable")
        number = normalize_destination(channel, destination)
        otp_rate_limiter.check_new_challenge(self.db, organization_id=self.org.id, destination=number, ip=self.meta.ip_address, session_key=session_key, policy=self.policy)
        now = utcnow()
        self.db.execute(update(OtpChallenge).where(
            OtpChallenge.organization_id == self.org.id, OtpChallenge.session_key == session_key, OtpChallenge.purpose == SIGN_IN,
            OtpChallenge.verified_at.is_(None), OtpChallenge.invalidated_at.is_(None)).values(invalidated_at=now))
        ch = OtpChallenge(organization_id=self.org.id, purpose=SIGN_IN, channel=channel, destination=number, code_hash="-", max_attempts=self.policy["max_attempts"],
                          expires_at=now, session_key=session_key, ip_address=self.meta.ip_address)
        self.db.add(ch)
        self.db.flush()
        code = self._issue(ch)
        self._deliver(ch, code)
        record_audit(self.db, action="patient.sign_in_code_sent", actor=None, organization_id=self.org.id, entity_type="otp_challenge", entity_id=ch.public_id,
                     after={"channel": channel, "destination": mask(channel, number), "provider": ch.provider}, meta=self.meta)
        self.db.flush()
        return self.describe(ch)

    def verify_sign_in(self, challenge_id: str, code: str, session_key: str) -> OtpChallenge:
        """The code is right: returns the challenge (its channel and the exact verified destination)."""
        ch = self._challenge(challenge_id, session_key)
        if ch.purpose != SIGN_IN:
            raise NotFoundError("This verification request was not found. Please request a new code.", code="otp_not_found")
        otp_verifier.verify(ch, code.strip())
        self.db.flush()
        return ch


def check_booking_token(db: Session, org: Organization, *, hold_id: str | None, session_key: str | None, customer_mobile: str | None,
                        customer_email: str | None, token: str | None, user: User | None) -> None:
    """Run before a public booking is created. Raises unless the contact detail being booked was verified."""
    if not booking_verification_required(db, org):
        return
    mobile = normalize_mobile(customer_mobile) if customer_mobile and customer_mobile.strip() else None
    email = customer_email.strip().lower() if customer_email and customer_email.strip() else None
    if user is not None:  # a signed-in customer's own, already verified contact details
        if user.mobile and user.mobile_verified_at and mobile == user.mobile:
            return
        if user.email and user.email_verified_at and email == user.email.lower() and not mobile:
            return
    if not token:
        raise ValidationFailed("Please verify your contact details with the code we send you.", code="contact_not_verified")
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ValidationFailed("Your verification expired. Please verify again.", code="contact_verification_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValidationFailed("Please verify your contact details again.", code="contact_not_verified") from exc
    if claims.get("typ") != TOKEN_TYPE or claims.get("org") != org.public_id or claims.get("hold") != hold_id or claims.get("sid") != session_key:
        raise ValidationFailed("This verification belongs to another booking. Please verify again.", code="contact_not_verified")
    booked = email if claims.get("ch") == "email" else mobile
    if not booked or booked != claims.get("dst"):
        raise ValidationFailed("The verified contact does not match the details in this booking. Please verify again.", code="contact_not_verified")
