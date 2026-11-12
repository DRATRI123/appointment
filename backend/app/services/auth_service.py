"""Authentication: OTP, password, Google, refresh rotation, sessions, password reset, verification."""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import OTPChannel, OTPPurpose, UserStatus
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDenied, RateLimited, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models import OTPVerification, User, UserSession
from app.repositories.otp import OTPRepository
from app.repositories.users import SessionRepository, UserRepository
from app.security.google import GoogleIdentity, get_google_verifier
from app.security.identifiers import normalize_email, normalize_mobile
from app.security.otp import OTPMessage, generate_otp, get_otp_provider, hash_otp, verify_otp_hash
from app.security.passwords import hash_password, needs_rehash, validate_password_policy, verify_password
from app.security.tokens import create_access_token, generate_refresh_token, hash_token
from app.services.audit_service import RequestMeta, record_audit

log = get_logger(__name__)

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
PASSWORD_RESET_TTL_MINUTES = 30
EMAIL_VERIFY_TTL_HOURS = 24


@dataclass
class AuthResult:
    user: User
    session: UserSession
    access_token: str
    refresh_token: str
    is_new_user: bool = False

    @property
    def expires_in(self) -> int:
        return get_settings().access_token_expire_minutes * 60


def classify_identifier(identifier: str) -> tuple[str, str]:
    """Return (normalized identifier, channel)."""
    if "@" in identifier:
        return normalize_email(identifier), OTPChannel.EMAIL
    return normalize_mobile(identifier), OTPChannel.SMS


class AuthService:
    def __init__(self, db: Session, meta: RequestMeta | None = None):
        self.db = db
        self.meta = meta or RequestMeta()
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)
        self.otps = OTPRepository(db)
        self.settings = get_settings()

    # ------------------------------------------------------------------ OTP
    def request_otp(self, identifier: str, purpose: str, user: User | None = None) -> tuple[OTPVerification, str | None]:
        ident, channel = classify_identifier(identifier)
        now = utcnow()
        latest = self.otps.latest(ident, purpose)
        if latest and latest.consumed_at is None:
            elapsed = (now - latest.created_at).total_seconds()
            if elapsed < self.settings.otp_resend_cooldown_seconds:
                wait = int(self.settings.otp_resend_cooldown_seconds - elapsed)
                raise RateLimited(f"Please wait {wait} seconds before requesting another code.", code="otp_cooldown")

        if purpose == OTPPurpose.LOGIN:
            existing = self.users.get_by_email(ident) if channel == OTPChannel.EMAIL else self.users.get_by_mobile(ident)
            if existing is not None:
                self._ensure_user_active(existing)
            # Unknown identifiers still receive a code: OTP login doubles as sign-up, and this
            # avoids leaking which numbers are registered.
        code = generate_otp()
        record = OTPVerification(
            user_id=user.id if user else None,
            identifier=ident,
            channel=channel,
            purpose=purpose,
            code_hash=hash_otp(ident, code),
            max_attempts=self.settings.otp_max_attempts,
            expires_at=now + timedelta(seconds=self.settings.otp_expire_seconds),
            ip_address=self.meta.ip_address,
        )
        provider = get_otp_provider()
        record.provider = provider.name
        record.provider_message_id = provider.send(OTPMessage(ident, channel, code, purpose))
        self.otps.add(record)
        debug_code = code if (provider.name == "console" and self.settings.app_env in {"development", "test"}) else None
        return record, debug_code

    def verify_otp(
        self, identifier: str, code: str, purpose: str, *, full_name: str | None = None, device_label: str | None = None
    ) -> AuthResult:
        ident, channel = classify_identifier(identifier)
        record = self.otps.latest_unconsumed(ident, purpose)
        if record is None:
            raise AuthenticationError("No active code for this identifier. Request a new one.", code="otp_not_found")
        now = utcnow()
        if record.expires_at < now:
            raise AuthenticationError("The code has expired. Request a new one.", code="otp_expired")
        if record.attempts >= record.max_attempts:
            raise AuthenticationError("Too many incorrect attempts. Request a new code.", code="otp_locked")
        if not verify_otp_hash(ident, code.strip(), record.code_hash):
            record.attempts += 1
            self.db.flush()
            remaining = record.max_attempts - record.attempts
            raise AuthenticationError(f"Incorrect code. {remaining} attempts left.", code="otp_incorrect")

        record.verified_at = now
        record.consumed_at = now

        is_new = False
        user = self.users.get_by_email(ident) if channel == OTPChannel.EMAIL else self.users.get_by_mobile(ident)
        if user is None:
            if purpose not in {OTPPurpose.LOGIN, OTPPurpose.REGISTER}:
                raise AuthenticationError("Account not found.", code="account_not_found")
            user = User(full_name=(full_name or "").strip() or "Customer", status=UserStatus.ACTIVE)
            if channel == OTPChannel.EMAIL:
                user.email = ident
            else:
                user.mobile = ident
            self.users.add(user)
            is_new = True
        else:
            self._ensure_user_active(user)
            if user.status == UserStatus.PENDING_VERIFICATION:
                user.status = UserStatus.ACTIVE
            if full_name and user.full_name in {"Customer", ""}:
                user.full_name = full_name.strip()

        if channel == OTPChannel.EMAIL and user.email_verified_at is None:
            user.email_verified_at = now
        if channel == OTPChannel.SMS and user.mobile_verified_at is None:
            user.mobile_verified_at = now
        record.user_id = user.id
        self._activate_invited_memberships(user)
        result = self._issue_session(user, device_label, is_new_user=is_new)
        record_audit(self.db, action="auth.login_otp", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return result

    # ------------------------------------------------------------- password
    def register_with_password(
        self, *, full_name: str, email: str, password: str, mobile: str | None, device_label: str | None
    ) -> AuthResult:
        email_n = normalize_email(email)
        validate_password_policy(password)
        if self.users.get_by_email(email_n):
            raise ConflictError("An account with this email already exists.", code="email_taken")
        mobile_n = normalize_mobile(mobile) if mobile else None
        if mobile_n and self.users.get_by_mobile(mobile_n):
            raise ConflictError("An account with this mobile number already exists.", code="mobile_taken")
        user = User(
            full_name=full_name.strip(),
            email=email_n,
            mobile=mobile_n,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE,
        )
        self.users.add(user)
        self._activate_invited_memberships(user)
        record_audit(self.db, action="auth.register", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return self._issue_session(user, device_label, is_new_user=True)

    def login_with_password(self, *, email: str, password: str, device_label: str | None) -> AuthResult:
        email_n = normalize_email(email)
        user = self.users.get_by_email(email_n)
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            raise AuthenticationError("Account temporarily locked. Try again later.", code="account_locked")
        if user is None or not verify_password(password, user.password_hash):
            if user is not None:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                    user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                    user.failed_login_attempts = 0
                    record_audit(self.db, action="auth.lockout", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
                self.db.flush()
            raise AuthenticationError("Invalid email or password.", code="invalid_credentials")
        self._ensure_user_active(user)
        if needs_rehash(user.password_hash or ""):
            user.password_hash = hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        self._activate_invited_memberships(user)
        record_audit(self.db, action="auth.login_password", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return self._issue_session(user, device_label)

    def change_password(self, user: User, *, current_password: str | None, new_password: str) -> None:
        if user.password_hash and not verify_password(current_password or "", user.password_hash):
            raise AuthenticationError("Current password is incorrect.", code="invalid_credentials")
        validate_password_policy(new_password)
        user.password_hash = hash_password(new_password)
        self.db.flush()
        record_audit(self.db, action="auth.password_changed", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)

    def request_password_reset(self, email: str) -> str | None:
        """Returns the raw token only for the console provider in dev/test; otherwise None."""
        email_n = normalize_email(email)
        user = self.users.get_by_email(email_n)
        if user is None or user.status == UserStatus.SUSPENDED:
            return None  # do not reveal whether the email exists
        token = secrets.token_urlsafe(32)
        record = OTPVerification(
            user_id=user.id,
            identifier=email_n,
            channel=OTPChannel.EMAIL,
            purpose=OTPPurpose.PASSWORD_RESET,
            code_hash=hash_token(token),
            max_attempts=1,
            expires_at=utcnow() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
            ip_address=self.meta.ip_address,
        )
        provider = get_otp_provider()
        record.provider = provider.name
        provider.send(OTPMessage(email_n, OTPChannel.EMAIL, token, OTPPurpose.PASSWORD_RESET))
        self.otps.add(record)
        record_audit(self.db, action="auth.password_reset_requested", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return token if (provider.name == "console" and self.settings.app_env in {"development", "test"}) else None

    def confirm_password_reset(self, token: str, new_password: str) -> User:
        record = self.otps.get_by_code_hash(OTPPurpose.PASSWORD_RESET, hash_token(token))
        if record is None or record.expires_at < utcnow() or record.user_id is None:
            raise AuthenticationError("Reset link is invalid or has expired.", code="reset_token_invalid")
        user = self.users.get(record.user_id)
        if user is None:
            raise AuthenticationError("Reset link is invalid or has expired.", code="reset_token_invalid")
        validate_password_policy(new_password)
        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        record.consumed_at = record.verified_at = utcnow()
        self.revoke_all_sessions(user, reason="password_reset")
        record_audit(self.db, action="auth.password_reset", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return user

    # ------------------------------------------------------- email verify
    def request_email_verification(self, user: User) -> str | None:
        if not user.email:
            raise ValidationFailed("No email address on this account.", code="no_email")
        if user.email_verified_at:
            raise ConflictError("Email is already verified.", code="already_verified")
        token = secrets.token_urlsafe(32)
        record = OTPVerification(
            user_id=user.id,
            identifier=user.email,
            channel=OTPChannel.EMAIL,
            purpose=OTPPurpose.VERIFY_EMAIL,
            code_hash=hash_token(token),
            max_attempts=1,
            expires_at=utcnow() + timedelta(hours=EMAIL_VERIFY_TTL_HOURS),
        )
        provider = get_otp_provider()
        record.provider = provider.name
        provider.send(OTPMessage(user.email, OTPChannel.EMAIL, token, OTPPurpose.VERIFY_EMAIL))
        self.otps.add(record)
        return token if (provider.name == "console" and self.settings.app_env in {"development", "test"}) else None

    def confirm_email_verification(self, token: str) -> User:
        record = self.otps.get_by_code_hash(OTPPurpose.VERIFY_EMAIL, hash_token(token))
        if record is None or record.expires_at < utcnow() or record.user_id is None:
            raise AuthenticationError("Verification link is invalid or has expired.", code="verify_token_invalid")
        user = self.users.get(record.user_id)
        if user is None:
            raise AuthenticationError("Verification link is invalid or has expired.", code="verify_token_invalid")
        user.email_verified_at = utcnow()
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
        record.consumed_at = record.verified_at = utcnow()
        self.db.flush()
        return user

    # --------------------------------------------------------------- google
    def login_with_google(self, id_token: str, device_label: str | None) -> AuthResult:
        identity: GoogleIdentity = get_google_verifier().verify(id_token)
        if not identity.email or not identity.email_verified:
            raise AuthenticationError("Google account email is not verified.", code="google_email_unverified")
        is_new = False
        user = self.users.get_by_google_sub(identity.sub)
        if user is None:
            user = self.users.get_by_email(identity.email)
            if user is None:
                user = User(
                    full_name=identity.name or identity.email.split("@")[0],
                    email=identity.email,
                    avatar_url=identity.picture,
                    status=UserStatus.ACTIVE,
                    email_verified_at=utcnow(),
                )
                self.users.add(user)
                is_new = True
            user.google_sub = identity.sub
        self._ensure_user_active(user)
        if user.email_verified_at is None:
            user.email_verified_at = utcnow()
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
        self._activate_invited_memberships(user)
        record_audit(self.db, action="auth.login_google", actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta)
        return self._issue_session(user, device_label, is_new_user=is_new)

    # ------------------------------------------------------------- sessions
    def refresh(self, refresh_token: str) -> AuthResult:
        token_hash = hash_token(refresh_token)
        session = self.sessions.get_by_token_hash(token_hash)
        now = utcnow()
        if session is None:
            raise AuthenticationError("Invalid refresh token.", code="refresh_invalid")
        if session.revoked_at is not None:
            # Reuse of a rotated token: assume theft and revoke the whole family.
            for s in self.sessions.list_family(session.family_id):
                if s.revoked_at is None:
                    s.revoked_at = now
                    s.revoked_reason = "token_reuse"
            self.db.flush()
            log.warning("auth.refresh_reuse_detected", family=session.family_id, user_id=session.user_id)
            raise AuthenticationError("Session is no longer valid. Please sign in again.", code="refresh_reused")
        if session.expires_at < now:
            session.revoked_at = now
            session.revoked_reason = "expired"
            self.db.flush()
            raise AuthenticationError("Session expired. Please sign in again.", code="refresh_expired")
        user = self.users.get(session.user_id)
        if user is None:
            raise AuthenticationError("Invalid refresh token.", code="refresh_invalid")
        self._ensure_user_active(user)
        # Rotate: revoke old, issue new row in the same family.
        session.revoked_at = now
        session.revoked_reason = "rotated"
        new_token = generate_refresh_token()
        new_session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(new_token),
            family_id=session.family_id,
            user_agent=self.meta.user_agent or session.user_agent,
            ip_address=self.meta.ip_address or session.ip_address,
            device_label=session.device_label,
            expires_at=session.expires_at,
            last_seen_at=now,
        )
        self.sessions.add(new_session)
        access = create_access_token(user_public_id=user.public_id, session_public_id=new_session.public_id)
        return AuthResult(user=user, session=new_session, access_token=access, refresh_token=new_token)

    def logout(self, session_public_id: str | None, refresh_token: str | None = None) -> None:
        session = None
        if refresh_token:
            session = self.sessions.get_by_token_hash(hash_token(refresh_token))
        if session is None and session_public_id:
            session = self.sessions.get_by_public_id(session_public_id)
        if session is None:
            return
        now = utcnow()
        for s in self.sessions.list_family(session.family_id):
            if s.revoked_at is None:
                s.revoked_at = now
                s.revoked_reason = "logout"
        self.db.flush()

    def list_sessions(self, user: User) -> list[UserSession]:
        """One entry per device: the newest active row of each family."""
        seen: set[str] = set()
        result = []
        for s in self.sessions.list_active_for_user(user.id):
            if s.family_id in seen:
                continue
            seen.add(s.family_id)
            result.append(s)
        return result

    def revoke_session(self, user: User, session_public_id: str) -> None:
        session = self.sessions.get_by_public_id(session_public_id)
        if session is None or session.user_id != user.id:
            raise PermissionDenied("Session not found.", code="session_not_found")
        now = utcnow()
        for s in self.sessions.list_family(session.family_id):
            if s.revoked_at is None:
                s.revoked_at = now
                s.revoked_reason = "revoked_by_user"
        self.db.flush()

    def revoke_all_sessions(self, user: User, reason: str = "revoked_all") -> int:
        now = utcnow()
        count = 0
        for s in self.sessions.list_active_for_user(user.id):
            s.revoked_at = now
            s.revoked_reason = reason
            count += 1
        self.db.flush()
        return count

    # -------------------------------------------------------------- helpers
    def _issue_session(self, user: User, device_label: str | None, *, is_new_user: bool = False) -> AuthResult:
        now = utcnow()
        refresh_token = generate_refresh_token()
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            family_id=str(uuid.uuid4()),
            user_agent=self.meta.user_agent,
            ip_address=self.meta.ip_address,
            device_label=device_label,
            expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            last_seen_at=now,
        )
        self.sessions.add(session)
        user.last_login_at = now
        self.db.flush()
        access = create_access_token(user_public_id=user.public_id, session_public_id=session.public_id)
        return AuthResult(user=user, session=session, access_token=access, refresh_token=refresh_token, is_new_user=is_new_user)

    @staticmethod
    def _ensure_user_active(user: User) -> None:
        if user.deleted_at is not None or user.status in {UserStatus.SUSPENDED, UserStatus.INACTIVE}:
            raise PermissionDenied("This account is suspended. Contact support.", code="account_suspended")

    def _activate_invited_memberships(self, user: User) -> None:
        for membership in user.memberships:
            if membership.status == "invited":
                membership.status = "active"
                membership.accepted_at = utcnow()
