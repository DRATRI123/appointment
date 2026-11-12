"""Google Sign-In ID token verification (adapter so tests can stub it)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


class GoogleTokenVerifier(Protocol):
    def verify(self, id_token: str) -> GoogleIdentity: ...


class JWKSGoogleTokenVerifier:
    def __init__(self) -> None:
        self._client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)

    def verify(self, id_token: str) -> GoogleIdentity:
        settings = get_settings()
        if not settings.google_client_id:
            raise AuthenticationError("Google login is not configured.", code="google_not_configured")
        try:
            signing_key = self._client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.google_client_id,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid Google token.", code="google_token_invalid") from exc
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise AuthenticationError("Invalid Google token issuer.", code="google_token_invalid")
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(claims.get("email", "")).lower(),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )


_verifier: GoogleTokenVerifier | None = None


def get_google_verifier() -> GoogleTokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = JWKSGoogleTokenVerifier()
    return _verifier


def set_google_verifier(verifier: GoogleTokenVerifier | None) -> None:
    global _verifier
    _verifier = verifier
