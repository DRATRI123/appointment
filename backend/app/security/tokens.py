"""JWT access tokens and opaque refresh tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.time import utcnow

# bandit B105 false positive: token type name, not a secret
ACCESS_TOKEN_TYPE = "access"  # nosec B105


def create_access_token(*, user_public_id: str, session_public_id: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": user_public_id,
        "sid": session_public_id,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.", code="token_invalid") from exc
    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise AuthenticationError("Invalid token type.", code="token_invalid")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Refresh tokens / reset tokens are stored hashed. SHA-256 is adequate for 256-bit random values."""
    settings = get_settings()
    return hashlib.sha256(f"{settings.secret_key}:{token}".encode()).hexdigest()
