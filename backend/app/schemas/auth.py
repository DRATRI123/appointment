from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.user import UserRead

OTPPurposeLiteral = Literal["login", "register", "verify_mobile", "verify_email"]


class OTPRequest(APIModel):
    identifier: str = Field(min_length=3, max_length=255, description="Mobile number or email address")
    purpose: OTPPurposeLiteral = "login"


class OTPRequestResponse(APIModel):
    identifier: str
    channel: str
    expires_in: int
    resend_in: int
    debug_code: str | None = Field(default=None, description="Only present with the console provider in development/test")


class OTPVerifyRequest(APIModel):
    identifier: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=10)
    purpose: OTPPurposeLiteral = "login"
    full_name: str | None = Field(default=None, max_length=160)
    device_label: str | None = Field(default=None, max_length=120)


class PasswordRegisterRequest(APIModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    mobile: str | None = Field(default=None, max_length=32)
    device_label: str | None = Field(default=None, max_length=120)


class PasswordLoginRequest(APIModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)
    device_label: str | None = Field(default=None, max_length=120)


class GoogleLoginRequest(APIModel):
    id_token: str = Field(min_length=20)
    device_label: str | None = Field(default=None, max_length=120)


class RefreshRequest(APIModel):
    refresh_token: str | None = None


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool = False
    user: UserRead


class PasswordResetRequest(APIModel):
    email: str = Field(max_length=255)


class PasswordResetConfirm(APIModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(APIModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerificationConfirm(APIModel):
    token: str = Field(min_length=10)


class SessionRead(APIModel):
    id: str
    device_label: str | None
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_seen_at: datetime | None
    expires_at: datetime
    is_current: bool = False


class MFAVerifyRequest(APIModel):
    mfa_token: str = Field(min_length=20, max_length=2048)
    code: str = Field(min_length=6, max_length=16, description="6-digit authenticator code, or a backup code like 7KQ4-M2XD")


class MFACodeRequest(APIModel):
    code: str = Field(min_length=6, max_length=16)


class MFADisableRequest(MFACodeRequest):
    password: str | None = Field(default=None, max_length=256)


class MFASetup(APIModel):
    secret: str
    otpauth_uri: str
    qr_data_url: str


class MFARecoveryCodes(APIModel):
    recovery_codes: list[str]


class MFAStatus(APIModel):
    enabled: bool
    enabled_at: datetime | None = None
    recovery_codes_left: int = 0
