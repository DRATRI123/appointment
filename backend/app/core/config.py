"""Application settings.

Every value is loaded from environment variables (or a local ``.env`` file). Nothing secret is
hard-coded. The app refuses to start outside development with an insecure ``SECRET_KEY``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
INSECURE_DEFAULT_SECRET = "change-me-to-a-random-string-of-at-least-32-bytes"


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
    job_backend: Literal["inline", "arq"] = "inline"

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
    notification_http_timeout_seconds: int = 15
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    # --- frontend ----------------------------------------------------------
    frontend_url: str = "http://localhost:3000"

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_security(self) -> "Settings":
        if self.app_env not in {"development", "test"}:
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be set to a random value of at least 32 characters "
                    "outside development."
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development.")
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
