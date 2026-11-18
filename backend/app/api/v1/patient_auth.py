"""Patients sign in on the clinic's website with a one-time code (no password).

The code goes through the clinic's own channels (its SMS / WhatsApp / email account, the platform's as fallback) with
the clinic's limits, expiry and resend rules (app/services/otp). After the code is right the patient is signed in with
the usual cookies and sees every booking made with that mobile number or email (app/services/customer_link.py).
The code is never returned by the API, in any environment.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app.api.deps import DB, AppSettings, Meta
from app.api.v1.auth import set_auth_cookies
from app.schemas.common import APIModel
from app.schemas.user import UserRead
from app.security.rate_limit import limiter
from app.services.auth_service import AuthService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/public/organizations/{slug}/patient-sign-in", tags=["patient sign-in"])


class SignInOptions(APIModel):
    channels: list[str]
    default_channel: str | None
    code_length: int


class SignInStart(APIModel):
    channel: str = Field(pattern=r"^(sms|whatsapp|email)$")
    destination: str = Field(min_length=3, max_length=254)
    session_key: str = Field(min_length=8, max_length=64)


class SignInSession(APIModel):
    session_key: str = Field(min_length=8, max_length=64)


class SignInCode(SignInSession):
    code: str = Field(min_length=4, max_length=10)


class SignInChallenge(APIModel):
    challenge_id: str
    channel: str
    destination: str = Field(description="Masked, e.g. +91•••••210")
    code_length: int
    expires_in_seconds: int
    resend_after_seconds: int
    resends_left: int


class SignedIn(APIModel):
    user: UserRead
    is_new_user: bool


def _org(db, slug: str):
    return OrganizationService(db).get_by_slug_public(slug)


@router.get("", response_model=SignInOptions, summary="How patients can get a sign-in code at this clinic")
def options(slug: str, db: DB) -> SignInOptions:
    from app.services.otp import load_policy
    from app.services.otp.otp_service import available_channels

    org = _org(db, slug)
    policy = load_policy(db, org)
    channels = available_channels(db, org, policy)
    default = policy.get("default_channel") if policy.get("default_channel") in channels else (channels[0] if channels else None)
    return SignInOptions(channels=([default] if default else []) + [c for c in channels if c != default], default_channel=default, code_length=policy["code_length"])


@router.post("/start", response_model=SignInChallenge, summary="Send a sign-in code by SMS, WhatsApp or email")
@limiter.limit("5/minute;30/hour")
def start(request: Request, response: Response, slug: str, payload: SignInStart, db: DB, meta: Meta):
    from app.services.otp import OTPService

    return OTPService(db, _org(db, slug), meta).start_sign_in(channel=payload.channel, destination=payload.destination, session_key=payload.session_key)


@router.post("/{challenge_id}/resend", response_model=SignInChallenge, summary="Send a new sign-in code for the same request")
@limiter.limit("5/minute;20/hour")
def resend(request: Request, response: Response, slug: str, challenge_id: str, payload: SignInSession, db: DB, meta: Meta):
    from app.services.otp import OTPService

    return OTPService(db, _org(db, slug), meta).resend(challenge_id, payload.session_key)


@router.post("/{challenge_id}/verify", response_model=SignedIn, summary="Check the code and sign the patient in")
@limiter.limit("10/minute")
def verify(request: Request, response: Response, slug: str, challenge_id: str, payload: SignInCode, db: DB, settings: AppSettings, meta: Meta) -> SignedIn:
    from app.services.otp import OTPService

    org = _org(db, slug)
    ch = OTPService(db, org, meta).verify_sign_in(challenge_id, payload.code, payload.session_key)
    result = AuthService(db, meta).sign_in_patient(org, ch.channel, ch.destination)  # staff with two-step sign-in: mfa_required
    set_auth_cookies(response, result, settings)
    return SignedIn(user=UserRead.model_validate(result.user), is_new_user=result.is_new_user)
