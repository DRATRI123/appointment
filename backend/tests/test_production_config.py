"""Startup guardrails: a staging/production server refuses settings that are only safe on a laptop."""
from __future__ import annotations

import base64
import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_PRODUCTION = {
    "app_env": "production",
    "secret_key": "s" * 48,
    "cookie_secure": True,
    "data_encryption_key": base64.b64encode(os.urandom(32)).decode(),
    "otp_pepper": "p" * 32,
    "cors_origins": ["https://clinic.example.com"],
    "trusted_hosts": ["clinic.example.com"],
    "forwarded_allow_ips": ["172.16.0.0/12"],
    "frontend_url": "https://clinic.example.com",
    "otp_provider": "msg91",
}


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """The test run itself sets APP_ENV, RATE_LIMIT_ENABLED and friends; each case starts from a blank slate."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**GOOD_PRODUCTION, **overrides})


def test_a_correct_production_configuration_starts():
    s = _settings()
    assert s.is_production and s.cookie_secure


@pytest.mark.parametrize(("override", "message"), [
    ({"secret_key": "change-me-to-a-random-string-of-at-least-32-bytes"}, "SECRET_KEY"),
    ({"secret_key": "short"}, "SECRET_KEY"),
    ({"cookie_secure": False}, "COOKIE_SECURE"),
    ({"debug": True}, "DEBUG"),
    ({"data_encryption_key": ""}, "DATA_ENCRYPTION_KEY must be set"),
    ({"data_encryption_key": base64.b64encode(b"too short").decode()}, "exactly 32"),
    ({"data_encryption_key": "not base64!!"}, "exactly 32"),
    ({"otp_pepper": ""}, "OTP_PEPPER"),
    ({"cors_origins": ["*"]}, "CORS_ORIGINS must list"),
    ({"cors_origins": ["http://clinic.example.com"]}, "CORS_ORIGINS must all start with https"),
    ({"forwarded_allow_ips": ["*"]}, "FORWARDED_ALLOW_IPS"),
    ({"trusted_hosts": ["*"]}, "TRUSTED_HOSTS"),
    ({"frontend_url": "http://clinic.example.com"}, "FRONTEND_URL"),
    ({"otp_provider": "console"}, "OTP_PROVIDER"),
    ({"webhook_allow_private_targets": True}, "WEBHOOK_ALLOW_PRIVATE_TARGETS"),
    ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED"),
    ({"storage_backend": "s3"}, "S3_BUCKET"),
])
def test_unsafe_production_settings_are_refused(override, message):
    with pytest.raises(ValidationError, match=message):
        _settings(**override)


def test_all_problems_are_reported_together():
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None, app_env="production")
    text = str(info.value)
    for name in ("SECRET_KEY", "COOKIE_SECURE", "DATA_ENCRYPTION_KEY", "OTP_PEPPER", "TRUSTED_HOSTS", "FRONTEND_URL", "OTP_PROVIDER"):
        assert name in text


def test_staging_may_use_console_codes_and_plain_hosts_but_not_weak_secrets():
    s = _settings(app_env="staging", otp_provider="console", trusted_hosts=["*"], frontend_url="http://staging.local", cors_origins=["http://staging.local"])
    assert s.app_env == "staging"
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(app_env="staging", secret_key="short")


def test_development_defaults_still_work():
    assert Settings(_env_file=None).app_env == "development"
