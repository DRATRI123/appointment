"""Application settings.

Every value is loaded from environment variables (or a local ``.env`` file). Nothing secret is
hard-coded. The app refuses to start outside development with an insecure ``SECRET_KEY``.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
# bandit B105 false positive: placeholder; rejected at startup outside development
INSECURE_DEFAULT_SECRET = "change-me-to-a-random-string-of-at-least-32-bytes"  # nosec B105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -------------------------------------------------------
    app_name: str = "Appointment Platform"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = False

    # --- security ----------------------------------------------------------
    secret_key: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    otp_expire_seconds: int = 300
    otp_resend_cooldown_seconds: int = 60
    otp_max_attempts: int = 5
    otp_length: int = 6
    otp_pepper: str = ""
    data_encryption_key: str = ""  # base64 32-byte key for field-level encryption (Phase 5)
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    # Only these peers may set X-Forwarded-For (the Next.js server / reverse proxy). Anyone else's header is ignored.
    forwarded_allow_ips: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["127.0.0.1", "::1"])
    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/minute"
    max_upload_size_mb: int = 5

    # --- database ----------------------------------------------------------
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- redis / jobs ------------------------------------------------------
    redis_url: str | None = None
    job_backend: Literal["inline"] = "inline"  # jobs run in the worker process (python -m app.workers.runner)

    # --- storage -----------------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = str(BASE_DIR / "uploads")
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # --- booking defaults (overridable per organization) -------------------
    booking_hold_minutes: int = 10
    payment_window_minutes: int = 30

    # --- providers (adapters) ---------------------------------------------
    otp_provider: str = "console"
    email_provider: str = "console"
    sms_provider: str = "console"
    whatsapp_provider: str = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str | None = None  # defaults to the organization name per message
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: int = 20
    # SMS: console | twilio | msg91. WhatsApp: console | meta | twilio. Credentials only via environment.
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_sms_from: str | None = None  # E.164 number or messaging service SID (MG...)
    twilio_whatsapp_from: str | None = None  # e.g. whatsapp:+14155238886
    msg91_auth_key: str | None = None
    msg91_sender_id: str | None = None
    msg91_route: str = "4"
    whatsapp_cloud_token: str | None = None
    whatsapp_cloud_phone_number_id: str | None = None
    whatsapp_cloud_api_version: str = "v21.0"
    otp_sms_template_id: str | None = None  # DLT / MSG91 flow id for the login-code SMS
    notification_max_attempts: int = 5
    # Developer API and webhooks
    api_key_default_rate_limit: int = 120  # requests per minute per key
    webhook_allow_private_targets: bool | None = None  # None = allowed only in development/test (localhost receivers)
    webhook_timeout_seconds: int = 10
    webhook_max_attempts: int = 8
    notification_http_timeout_seconds: int = 15
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    # Google Calendar OAuth callback. Defaults to <FRONTEND_URL>/api/v1/integrations/google/callback (the
    # frontend proxies /api to the API). Register exactly this URL in Google Cloud Console.
    google_calendar_redirect_uri: str | None = None
    calendar_sync_days_ahead: int = 60
    integration_http_timeout_seconds: int = 20

    # --- monitoring --------------------------------------------------------
    metrics_token: str | None = None  # /metrics is disabled (404) unless this is set; scrape with "Authorization: Bearer <token>"
    sentry_dsn: str | None = None  # optional error tracking; personal data is scrubbed before sending
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- frontend ----------------------------------------------------------
    frontend_url: str = "http://localhost:3000"

    @field_validator("cors_origins", "trusted_hosts", "forwarded_allow_ips", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        """Refuse to start a staging or production server with settings that are only safe on a laptop.

        Every problem is reported at once so a deployment can be fixed in one pass."""
        if self.app_env in {"development", "test"}:
            return self
        problems: list[str] = []
        if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a random value of at least 32 characters")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true (cookies only over HTTPS)")
        if self.debug:
            problems.append("DEBUG must be false")
        if not self.data_encryption_key:
            problems.append("DATA_ENCRYPTION_KEY must be set (clinical notes are encrypted with it)")
        else:
            try:
                if len(base64.b64decode(self.data_encryption_key, validate=True)) != 32:
                    raise ValueError
            except ValueError:
                problems.append("DATA_ENCRYPTION_KEY must be base64 of exactly 32 random bytes")
        if len(self.otp_pepper) < 16:
            problems.append("OTP_PEPPER must be a random value of at least 16 characters")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list your real web addresses, not *")
        if "*" in self.forwarded_allow_ips:
            problems.append("FORWARDED_ALLOW_IPS must list your proxy addresses, not * (clients could fake their IP)")
        if self.app_env == "production":
            if self.trusted_hosts == ["*"] or "*" in self.trusted_hosts:
                problems.append("TRUSTED_HOSTS must list your domain names, not *")
            if not self.frontend_url.startswith("https://"):
                problems.append("FRONTEND_URL must start with https://")
            if any(not o.startswith("https://") for o in self.cors_origins):
                problems.append("CORS_ORIGINS must all start with https://")
            if self.otp_provider == "console":
                problems.append("OTP_PROVIDER cannot be console (login codes would only be written to the server log)")
            if self.webhook_allow_private_targets:
                problems.append("WEBHOOK_ALLOW_PRIVATE_TARGETS must be unset or false")
            if not self.rate_limit_enabled:
                problems.append("RATE_LIMIT_ENABLED must be true")
        if self.metrics_token is not None and len(self.metrics_token) < 24:
            problems.append("METRICS_TOKEN must be at least 24 random characters (or unset to disable /metrics)")
        if self.storage_backend == "s3" and not self.s3_bucket:
            problems.append("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if problems:
            raise ValueError(f"Unsafe {self.app_env} configuration:\n  - " + "\n  - ".join(problems))
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
