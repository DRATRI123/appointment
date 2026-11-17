"""Two-step sign-in (MFA) with an authenticator app and single-use backup codes.

Sign-in: password, mobile code or Google as before; if the account has two-step sign-in on, the response is
``401 mfa_required`` with a short-lived ``mfa_token`` instead of a session. ``POST /auth/mfa/verify`` with that token and
a 6-digit authenticator code (or a backup code) issues the session. Wrong codes count towards the same lockout as wrong
passwords. A clinic can require it for owners and administrators (setting ``security.require_admin_mfa``).
"""
from __future__ import annotations

import base64
import io
import secrets
from datetime import timedelta
from typing import Any

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import SystemRole
from app.core.exceptions import AuthenticationError, ConflictError, ValidationFailed
from app.core.time import utcnow
from app.models import User
from app.security import totp
from app.security.crypto import decrypt_text, encrypt_text
from app.security.passwords import verify_password
from app.services.audit_service import RequestMeta, record_audit

MFA_TOKEN_TYPE = "mfa"  # nosec B105 - token type name, not a secret
MFA_TOKEN_MINUTES = 5
ADMIN_ROLES = frozenset({SystemRole.ORG_OWNER.value, SystemRole.ORG_ADMIN.value})


class MFARequired(AuthenticationError):
    code = "mfa_required"

    def __init__(self, token: str):
        super().__init__("Enter the 6-digit code from your authenticator app.", code="mfa_required",
                         data={"mfa_token": token, "mfa_token_expires_in": MFA_TOKEN_MINUTES * 60})


def issue_mfa_token(user: User, device_label: str | None, panel_organization: str | None = None) -> str:
    """``panel_organization``: public id of the clinic whose embedded panel the person is signing in to (or None)."""
    s = get_settings()
    now = utcnow()
    payload = {"sub": user.public_id, "typ": MFA_TOKEN_TYPE, "dev": device_label, "iat": int(now.timestamp()),
               "exp": int((now + timedelta(minutes=MFA_TOKEN_MINUTES)).timestamp()), "jti": secrets.token_hex(8)}
    if panel_organization:
        payload["pnl"] = panel_organization
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def _decode_mfa_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("The sign-in took too long. Please sign in again.", code="mfa_token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Please sign in again.", code="mfa_token_invalid") from exc
    if payload.get("typ") != MFA_TOKEN_TYPE:
        raise AuthenticationError("Please sign in again.", code="mfa_token_invalid")
    return payload


def _pepper() -> str:
    s = get_settings()
    return s.otp_pepper or s.secret_key


def _qr_data_url(uri: str) -> str:
    import qrcode

    img = qrcode.make(uri, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class MFAService:
    def __init__(self, db: Session, meta: RequestMeta | None = None):
        self.db, self.meta = db, meta

    def _audit(self, user: User, action: str, **after) -> None:
        record_audit(self.db, action=action, actor=user, entity_type="user", entity_id=user.public_id, meta=self.meta, after=after or None)

    # ------------------------------------------------------------------ enrolment
    def start_setup(self, user: User) -> dict[str, Any]:
        """A new secret, not active until a code from it is confirmed. Starting again replaces an unconfirmed one."""
        if user.mfa_enabled_at is not None:
            raise ConflictError("Two-step sign-in is already on. Turn it off first to move it to a new phone.", code="mfa_already_enabled")
        secret = totp.new_secret()
        user.mfa_secret = encrypt_text(secret)
        user.mfa_last_step = None
        self.db.flush()
        account = user.email or user.mobile or user.public_id
        uri = totp.provisioning_uri(secret, account=account, issuer=get_settings().app_name)
        return {"secret": secret, "otpauth_uri": uri, "qr_data_url": _qr_data_url(uri)}

    def enable(self, user: User, code: str) -> list[str]:
        if user.mfa_enabled_at is not None:
            raise ConflictError("Two-step sign-in is already on.", code="mfa_already_enabled")
        if not user.mfa_secret:
            raise ValidationFailed("Start the set-up first.", code="mfa_setup_missing")
        step = totp.verify(decrypt_text(user.mfa_secret), code, last_step=None)
        if step is None:
            raise ValidationFailed("That code is not right. Check the time on your phone and try the newest code.", code="mfa_code_invalid")
        codes = totp.new_recovery_codes()
        user.mfa_recovery_hashes = [totp.hash_recovery_code(c, _pepper()) for c in codes]
        user.mfa_last_step = step
        user.mfa_enabled_at = utcnow()
        self._audit(user, "auth.mfa_enabled")
        self.db.flush()
        return codes

    def disable(self, user: User, *, code: str, password: str | None) -> None:
        if user.mfa_enabled_at is None:
            return
        if user.password_hash and not verify_password(password or "", user.password_hash):
            raise AuthenticationError("Your password is not right.", code="invalid_credentials")
        if not self._check_code(user, code):
            raise ValidationFailed("That code is not right.", code="mfa_code_invalid")
        if self._required_by_a_clinic(user):
            raise ConflictError("A clinic you manage requires two-step sign-in for administrators.", code="mfa_required_by_organization")
        user.mfa_secret = None
        user.mfa_enabled_at = None
        user.mfa_last_step = None
        user.mfa_recovery_hashes = None
        self._audit(user, "auth.mfa_disabled")
        self.db.flush()

    def regenerate_recovery_codes(self, user: User, code: str) -> list[str]:
        if user.mfa_enabled_at is None:
            raise ValidationFailed("Two-step sign-in is off.", code="mfa_not_enabled")
        if not self._check_code(user, code, allow_recovery=False):
            raise ValidationFailed("That code is not right.", code="mfa_code_invalid")
        codes = totp.new_recovery_codes()
        user.mfa_recovery_hashes = [totp.hash_recovery_code(c, _pepper()) for c in codes]
        self._audit(user, "auth.mfa_recovery_codes_regenerated")
        self.db.flush()
        return codes

    # ------------------------------------------------------------------ sign-in
    def complete_sign_in(self, mfa_token: str, code: str, *, panel_organization=None):
        """``panel_organization``: the clinic whose embedded panel this sign-in is for. A token started there finishes
        only there (and an ordinary sign-in only at the ordinary endpoint)."""
        from app.services.auth_service import LOCKOUT_MINUTES, MAX_FAILED_LOGINS, AuthService

        payload = _decode_mfa_token(mfa_token)
        if payload.get("pnl") != (panel_organization.public_id if panel_organization is not None else None):
            raise AuthenticationError("Please sign in again.", code="mfa_token_invalid")
        user = self.db.query(User).filter(User.public_id == payload["sub"]).one_or_none()
        now = utcnow()
        if user is None or user.mfa_enabled_at is None:
            raise AuthenticationError("Please sign in again.", code="mfa_token_invalid")
        if user.locked_until and user.locked_until > now:
            raise AuthenticationError("Account temporarily locked. Try again later.", code="account_locked")
        AuthService._ensure_user_active(user)
        if not self._check_code(user, code):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                self._audit(user, "auth.lockout", reason="mfa")
            self.db.flush()
            raise AuthenticationError("That code is not right.", code="mfa_code_invalid", persist=True)
        user.failed_login_attempts = 0
        user.locked_until = None
        self._audit(user, "auth.login_mfa")
        return AuthService(self.db, self.meta or RequestMeta())._issue_session(user, payload.get("dev"), mfa_passed=True,
                                                                                 panel_organization=panel_organization)

    # ------------------------------------------------------------------ helpers
    def _check_code(self, user: User, code: str, *, allow_recovery: bool = True) -> bool:
        if not user.mfa_secret:
            return False
        step = totp.verify(decrypt_text(user.mfa_secret), code, last_step=user.mfa_last_step)
        if step is not None:
            user.mfa_last_step = step
            return True
        if allow_recovery and user.mfa_recovery_hashes and any(ch.isalpha() for ch in code):
            wanted = totp.hash_recovery_code(code, _pepper())
            remaining = [h for h in user.mfa_recovery_hashes if not secrets.compare_digest(h, wanted)]
            if len(remaining) < len(user.mfa_recovery_hashes):
                user.mfa_recovery_hashes = remaining  # each backup code works once
                self._audit(user, "auth.mfa_recovery_code_used", remaining=len(remaining))
                return True
        return False

    def _required_by_a_clinic(self, user: User) -> bool:
        from app.services.organization_service import OrganizationService

        orgs = OrganizationService(self.db)
        return any(m.role and m.role.code in ADMIN_ROLES and admin_mfa_required(orgs.get_settings(m.organization)) for m in user.memberships
                   if m.organization is not None and m.organization.deleted_at is None)


def admin_mfa_required(settings: dict[str, Any]) -> bool:
    return bool((settings.get("security") or {}).get("require_admin_mfa", False))
