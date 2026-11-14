"""Mobile number verification for public (guest) bookings.

Flow, all on the public booking page and without creating an account or a login session:

1. The customer reserves a slot (a hold) and enters their mobile number.
2. ``request_code``: a 6-digit code is sent by SMS. Reuses the platform OTP machinery: HMAC-hashed codes, expiry,
   resend cool-down, attempt limit, plus an hourly cap per number and per-IP route limits.
3. ``confirm_code``: the correct code returns a short-lived signed token bound to this clinic, this hold and this
   mobile number.
4. The booking request carries the token; the server checks it against the hold and the mobile number being booked.

The token is useless for anything else: another hold, another number, another clinic, or after it expires.
Signed-in customers whose account mobile is already verified skip the code for that same number.
"""
from __future__ import annotations

from datetime import timedelta

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import HoldStatus, OTPPurpose
from app.core.exceptions import AuthenticationError, PermissionDenied, RateLimited, SlotUnavailable, ValidationFailed
from app.core.time import utcnow
from app.models import BookingHold, Organization, OTPVerification, User
from app.repositories.otp import OTPRepository
from app.security.identifiers import normalize_mobile
from app.security.otp import verify_otp_hash
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService

# The JWT "typ" claim for these tokens (bandit mistakes the name for a password).
TOKEN_TYPE = "booking_mobile"  # nosec B105
TOKEN_MINUTES = 30
MAX_CODES_PER_HOUR = 5  # per mobile number, on top of the resend cool-down and per-IP route limits


def verification_required(db: Session, org: Organization) -> bool:
    return bool(OrganizationService(db).get_settings(org, "booking")["booking"].get("require_mobile_verification", True))


def _mobile(raw: str | None) -> str:
    if not raw or not raw.strip():
        raise ValidationFailed("Enter your mobile number.", code="mobile_required")
    return normalize_mobile(raw)  # raises ValidationFailed(code="invalid_mobile")


class BookingVerificationService:
    def __init__(self, db: Session, org: Organization, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.meta = meta or RequestMeta()
        self.settings = get_settings()

    def _hold(self, hold_id: str, session_key: str) -> BookingHold:
        hold = self.db.scalar(select(BookingHold).where(BookingHold.public_id == hold_id, BookingHold.organization_id == self.org.id))
        if hold is None:
            raise ValidationFailed("Choose a time first.", code="hold_not_found")
        if hold.session_key != session_key:
            raise PermissionDenied("This reservation belongs to another browser session.", code="hold_mismatch")
        if hold.status != HoldStatus.ACTIVE or hold.expires_at < utcnow():
            raise SlotUnavailable("Your reserved time has expired. Please choose the time again.", code="hold_expired")
        return hold

    # ----------------------------------------------------------------------------------------- send
    def request_code(self, *, mobile: str, hold_id: str, session_key: str) -> str | None:
        """Send a code to ``mobile``. Returns the code only in development/test with the console provider."""
        from app.services.auth_service import AuthService

        number = _mobile(mobile)
        self._hold(hold_id, session_key)
        hour_ago = utcnow() - timedelta(hours=1)
        sent = self.db.scalar(select(func.count()).select_from(OTPVerification).where(
            OTPVerification.identifier == number, OTPVerification.purpose == OTPPurpose.BOOKING, OTPVerification.created_at >= hour_ago)) or 0
        if sent >= MAX_CODES_PER_HOUR:
            raise RateLimited("Too many codes were sent to this number. Please try again in an hour.", code="otp_hourly_limit")
        _, debug_code = AuthService(self.db, self.meta).request_otp(number, OTPPurpose.BOOKING)
        record_audit(self.db, action="booking.mobile_code_sent", actor=None, organization_id=self.org.id, entity_type="booking_hold",
                     entity_id=hold_id, meta=self.meta)
        return debug_code

    # -------------------------------------------------------------------------------------- confirm
    def confirm_code(self, *, mobile: str, code: str, hold_id: str, session_key: str) -> tuple[str, str]:
        """Check the code; returns (token, normalized mobile)."""
        number = _mobile(mobile)
        hold = self._hold(hold_id, session_key)
        record = OTPRepository(self.db).latest_unconsumed(number, OTPPurpose.BOOKING)
        if record is None:
            raise AuthenticationError("No active code for this number. Request a new one.", code="otp_not_found")
        now = utcnow()
        if record.expires_at < now:
            raise AuthenticationError("The code has expired. Request a new one.", code="otp_expired")
        if record.attempts >= record.max_attempts:
            raise AuthenticationError("Too many incorrect attempts. Request a new code.", code="otp_locked")
        if not verify_otp_hash(number, (code or "").strip(), record.code_hash):
            record.attempts += 1
            self.db.flush()
            remaining = record.max_attempts - record.attempts
            # persist: the attempt counter must survive the error response, or guessing would be unlimited
            raise AuthenticationError(f"Incorrect code. {remaining} attempts left.", code="otp_incorrect", persist=True)
        record.verified_at = now
        record.consumed_at = now
        self.db.flush()
        token = jwt.encode({
            "typ": TOKEN_TYPE, "org": self.org.public_id, "hold": hold.public_id, "mobile": number,
            "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=TOKEN_MINUTES)).timestamp()),
        }, self.settings.secret_key, algorithm="HS256")
        return token, number

    # ---------------------------------------------------------------------------------------- check
    def check_booking(self, *, hold_id: str | None, customer_mobile: str | None, token: str | None, user: User | None) -> None:
        """Called before a public booking is created. Raises unless the mobile number being booked is verified."""
        if not verification_required(self.db, self.org):
            return
        if user is not None and user.mobile and user.mobile_verified_at is not None:
            if not customer_mobile or _mobile(customer_mobile) == user.mobile:
                return  # the signed-in customer's own, already verified number
        number = _mobile(customer_mobile)
        if not token:
            raise ValidationFailed("Please verify your mobile number with the code we send you.", code="mobile_not_verified")
        try:
            claims = jwt.decode(token, self.settings.secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise ValidationFailed("Your mobile verification expired. Please verify again.", code="mobile_verification_expired") from exc
        except jwt.InvalidTokenError as exc:
            raise ValidationFailed("Please verify your mobile number again.", code="mobile_not_verified") from exc
        if claims.get("typ") != TOKEN_TYPE or claims.get("org") != self.org.public_id or claims.get("hold") != hold_id or claims.get("mobile") != number:
            raise ValidationFailed("The verified number does not match this booking. Please verify again.", code="mobile_not_verified")
