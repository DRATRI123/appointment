"""OTP generation, hashing and provider adapters.

Providers implement ``OTPProvider.send``; swapping SMS vendors never touches authentication logic.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def generate_otp(length: int | None = None) -> str:
    length = length or get_settings().otp_length
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(identifier: str, code: str) -> str:
    settings = get_settings()
    key = (settings.otp_pepper or settings.secret_key).encode()
    return hmac.new(key, f"{identifier}:{code}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(identifier: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(identifier, code), code_hash)


@dataclass
class OTPMessage:
    identifier: str
    channel: str
    code: str
    purpose: str


class OTPProvider(Protocol):
    name: str

    def send(self, message: OTPMessage) -> str | None:
        """Send the OTP and return a provider message id when available."""


@dataclass
class ConsoleOTPProvider:
    """Development provider: logs the code and keeps the last messages in memory (used by tests)."""

    name: str = "console"
    sent: list[OTPMessage] = field(default_factory=list)

    def send(self, message: OTPMessage) -> str | None:
        self.sent.append(message)
        if len(self.sent) > 100:
            del self.sent[:-100]
        log.info("otp.console", identifier=message.identifier, purpose=message.purpose, code=message.code)
        return None

    def last_code_for(self, identifier: str) -> str | None:
        for message in reversed(self.sent):
            if message.identifier == identifier:
                return message.code
        return None


_console_provider = ConsoleOTPProvider()
_PROVIDERS: dict[str, OTPProvider] = {"console": _console_provider}


def register_otp_provider(provider: OTPProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_otp_provider() -> OTPProvider:
    name = get_settings().otp_provider
    if name == "notifications" and name not in _PROVIDERS:
        from app.notifications.otp import NotificationOTPProvider

        register_otp_provider(NotificationOTPProvider())
    try:
        return _PROVIDERS[name]
    except KeyError as exc:
        raise RuntimeError(f"OTP provider '{name}' is not registered. Available: {sorted(_PROVIDERS)}") from exc


def get_console_provider() -> ConsoleOTPProvider:
    return _console_provider
