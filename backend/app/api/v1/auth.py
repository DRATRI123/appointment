from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    DB,
    AppSettings,
    CurrentUser,
    Meta,
)
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.ids import random_token
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailVerificationConfirm,
    GoogleLoginRequest,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SessionRead,
    TokenResponse,
)
from app.schemas.common import Message
from app.schemas.user import UserRead
from app.security.rate_limit import limiter
from app.services.auth_service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_kwargs(settings: Settings) -> dict:
    return {"secure": settings.cookie_secure, "samesite": "lax", "domain": settings.cookie_domain, "path": "/"}


def set_auth_cookies(response: Response, result: AuthResult, settings: Settings) -> None:
    base = _cookie_kwargs(settings)
    response.set_cookie(ACCESS_COOKIE, result.access_token, max_age=result.expires_in, httponly=True, **base)
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        **{**base, "path": f"{settings.api_v1_prefix}/auth"},
    )
    # Double-submit CSRF token: readable by JS, compared to the X-CSRF-Token header on unsafe requests.
    response.set_cookie(CSRF_COOKIE, random_token(24), max_age=settings.refresh_token_expire_days * 86400, httponly=False, **base)


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    base = _cookie_kwargs(settings)
    response.delete_cookie(ACCESS_COOKIE, domain=base["domain"], path="/")
    response.delete_cookie(REFRESH_COOKIE, domain=base["domain"], path=f"{settings.api_v1_prefix}/auth")
    response.delete_cookie(CSRF_COOKIE, domain=base["domain"], path="/")


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
        is_new_user=result.is_new_user,
        user=UserRead.model_validate(result.user),
    )


@router.post("/otp/request", response_model=OTPRequestResponse, summary="Send a one-time code to a mobile or email")
@limiter.limit("5/minute")
def request_otp(request: Request, response: Response, payload: OTPRequest, db: DB, settings: AppSettings, meta: Meta) -> OTPRequestResponse:
    record, debug_code = AuthService(db, meta).request_otp(payload.identifier, payload.purpose)
    return OTPRequestResponse(
        identifier=record.identifier,
        channel=record.channel,
        expires_in=settings.otp_expire_seconds,
        resend_in=settings.otp_resend_cooldown_seconds,
        debug_code=debug_code,
    )


@router.post("/otp/verify", response_model=TokenResponse, summary="Verify the code and sign in (creates the account on first login)")
@limiter.limit("10/minute")
def verify_otp(request: Request, payload: OTPVerifyRequest, response: Response, db: DB, settings: AppSettings, meta: Meta) -> TokenResponse:
    result = AuthService(db, meta).verify_otp(
        payload.identifier, payload.code, payload.purpose, full_name=payload.full_name, device_label=payload.device_label
    )
    set_auth_cookies(response, result, settings)
    return _token_response(result)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, summary="Register with email and password")
@limiter.limit("5/minute")
def register(request: Request, payload: PasswordRegisterRequest, response: Response, db: DB, settings: AppSettings, meta: Meta) -> TokenResponse:
    result = AuthService(db, meta).register_with_password(
        full_name=payload.full_name, email=payload.email, password=payload.password, mobile=payload.mobile,
        device_label=payload.device_label,
    )
    set_auth_cookies(response, result, settings)
    return _token_response(result)


@router.post("/login", response_model=TokenResponse, summary="Sign in with email and password")
@limiter.limit("10/minute")
def login(request: Request, payload: PasswordLoginRequest, response: Response, db: DB, settings: AppSettings, meta: Meta) -> TokenResponse:
    result = AuthService(db, meta).login_with_password(email=payload.email, password=payload.password, device_label=payload.device_label)
    set_auth_cookies(response, result, settings)
    return _token_response(result)


@router.post("/google", response_model=TokenResponse, summary="Sign in with a Google ID token")
@limiter.limit("10/minute")
def google_login(request: Request, payload: GoogleLoginRequest, response: Response, db: DB, settings: AppSettings, meta: Meta) -> TokenResponse:
    result = AuthService(db, meta).login_with_google(payload.id_token, payload.device_label)
    set_auth_cookies(response, result, settings)
    return _token_response(result)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the refresh token and get a new access token")
@limiter.limit("30/minute")
def refresh(request: Request, response: Response, db: DB, settings: AppSettings, meta: Meta, payload: RefreshRequest | None = None) -> TokenResponse:
    token = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthenticationError("Refresh token missing.", code="refresh_missing")
    try:
        result = AuthService(db, meta).refresh(token)
    except AuthenticationError:
        clear_auth_cookies(response, settings)
        raise
    set_auth_cookies(response, result, settings)
    return _token_response(result)


@router.post("/logout", response_model=Message, summary="Sign out of the current device")
def logout(request: Request, response: Response, db: DB, settings: AppSettings, meta: Meta) -> Message:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    session_id = None
    try:
        from app.api.deps import get_optional_user  # local import to avoid cycle at module import time

        user = get_optional_user(request, db)
        session_id = getattr(request.state, "session_public_id", None) if user else None
    except Exception:  # expired/invalid token still allows logout
        session_id = None
    AuthService(db, meta).logout(session_id, refresh_token)
    clear_auth_cookies(response, settings)
    return Message(detail="Signed out.")


@router.get("/sessions", response_model=list[SessionRead], summary="List active devices")
def list_sessions(request: Request, db: DB, user: CurrentUser, meta: Meta) -> list[SessionRead]:
    current = getattr(request.state, "session_public_id", None)
    out = []
    for s in AuthService(db, meta).list_sessions(user):
        item = SessionRead(
            id=s.public_id, device_label=s.device_label, user_agent=s.user_agent, ip_address=s.ip_address,
            created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at,
            is_current=(s.public_id == current),
        )
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", response_model=Message, summary="Revoke a device session")
def revoke_session(session_id: str, db: DB, user: CurrentUser, meta: Meta) -> Message:
    AuthService(db, meta).revoke_session(user, session_id)
    return Message(detail="Session revoked.")


@router.post("/sessions/revoke-all", response_model=Message, summary="Sign out everywhere")
def revoke_all(response: Response, db: DB, user: CurrentUser, settings: AppSettings, meta: Meta) -> Message:
    count = AuthService(db, meta).revoke_all_sessions(user)
    clear_auth_cookies(response, settings)
    return Message(detail=f"Revoked {count} session(s).")


@router.post("/password/change", response_model=Message, summary="Change (or set) password")
def change_password(payload: ChangePasswordRequest, db: DB, user: CurrentUser, meta: Meta) -> Message:
    AuthService(db, meta).change_password(user, current_password=payload.current_password, new_password=payload.new_password)
    return Message(detail="Password updated.")


@router.post("/password/forgot", response_model=Message, summary="Request a password reset link")
@limiter.limit("5/minute")
def forgot_password(request: Request, response: Response, payload: PasswordResetRequest, db: DB, meta: Meta) -> Message:
    token = AuthService(db, meta).request_password_reset(payload.email)
    detail = "If an account exists for this email, a reset link has been sent."
    if token:
        detail += f" [debug token: {token}]"
    return Message(detail=detail)


@router.post("/password/reset", response_model=Message, summary="Reset password with the emailed token")
@limiter.limit("5/minute")
def reset_password(request: Request, response: Response, payload: PasswordResetConfirm, db: DB, meta: Meta) -> Message:
    AuthService(db, meta).confirm_password_reset(payload.token, payload.new_password)
    return Message(detail="Password reset. Please sign in again.")


@router.post("/email/verify/request", response_model=Message, summary="Send an email verification link")
@limiter.limit("5/minute")
def request_email_verification(request: Request, response: Response, db: DB, user: CurrentUser, meta: Meta) -> Message:
    token = AuthService(db, meta).request_email_verification(user)
    detail = "Verification email sent."
    if token:
        detail += f" [debug token: {token}]"
    return Message(detail=detail)


@router.post("/email/verify/confirm", response_model=Message, summary="Confirm email verification")
def confirm_email_verification(payload: EmailVerificationConfirm, db: DB, meta: Meta) -> Message:
    AuthService(db, meta).confirm_email_verification(payload.token)
    return Message(detail="Email verified.")
