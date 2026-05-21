from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class AuthConfig(BaseModel):
    local_login_enabled: bool = True
    signup_enabled: bool = True
    email_verification_required: bool = True
    password_min_length: int = 10
    mfa_required_for_admins: bool = False


class GoogleOidcConfig(BaseModel):
    enabled: bool = False
    client_id_env: str = "IPRL_CAE_GOOGLE_OIDC_CLIENT_ID"
    client_secret_env: str = "IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET"
    issuer: str = "https://accounts.google.com"
    discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    redirect_path: str = "/auth/google/callback"
    scopes: list[str] = ["openid", "email", "profile"]
    allowed_domains: list[str] = []
    auto_provision_default: bool = False


class SsoConfig(BaseModel):
    enabled: bool = True
    default_provider: str = "google"
    state_ttl_minutes: int = 10
    access_token_minutes: int = 480
    allowed_redirect_hosts: list[str] = ["localhost:3000", "127.0.0.1:3000"]
    google: GoogleOidcConfig = Field(default_factory=GoogleOidcConfig)


class MailConfig(BaseModel):
    provider: str = "console"
    from_email: str = "no-reply@example.local"
    smtp_host_env: str = "IPRL_CAE_SMTP_HOST"
    smtp_port_env: str = "IPRL_CAE_SMTP_PORT"
    smtp_user_env: str = "IPRL_CAE_SMTP_USER"
    smtp_password_env: str = "IPRL_CAE_SMTP_PASSWORD"


class OcrConfig(BaseModel):
    enabled: bool = True
    require_human_review: bool = True
    tesseract_cmd_env: str = "TESSERACT_CMD"
    tessdata_prefix_env: str = "TESSDATA_PREFIX"
    store_full_text: bool = False
    max_pages_per_file: int = 50


class ConnectorConfig(BaseModel):
    commercial_connectors_enabled: bool = False
    demo_connector_enabled: bool = True
    manual_export_enabled: bool = True
    erp_connectors_enabled: bool = False
    rpa_enabled: bool = False
    rpa_requires_manual_approval: bool = True


class JobsConfig(BaseModel):
    backend: str = "redis"
    queue_name: str = "iprl-cae"
    retry_attempts: int = 3
    retry_backoff_seconds: int = 60


class RetentionConfig(BaseModel):
    audit_log_days: int = 1825
    rejected_document_days: int = 365
    expired_document_days: int = 1825
    ocr_intake_days: int = 90


class FeatureFlags(BaseModel):
    worker_bulk_upload: bool = True
    worker_erp_import: bool = False
    platform_api_connectors: bool = False
    platform_rpa_connectors: bool = False
    google_sso: bool = True
    saas_reseller_mode: bool = True
    system_admin_console: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IPRL_CAE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    config_file: str | None = Field(default=None, alias="IPRL_CAE_CONFIG_FILE")
    app_name: str = "IPRL/CAE Hub"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://iprl_cae:change-me@localhost:5432/iprl_cae"
    redis_url: str = "redis://localhost:6379/0"
    document_storage_path: str = "./storage/documents"
    max_upload_bytes: int = 50 * 1024 * 1024
    secret_key: str = Field(default="change-this-in-production-use-at-least-32-bytes", repr=False)
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    sso_state_ttl_minutes: int = 10
    sso_access_token_minutes: int = 480
    email_verification_ttl_minutes: int = 1440
    auth_dev_tokens_enabled: bool = False
    trusted_header_auth_enabled: bool = False
    google_oidc_client_id: str | None = None
    google_oidc_client_secret: str | None = Field(default=None, repr=False)
    cors_origins_raw: str = Field(
        default="http://localhost:3000",
        alias="IPRL_CAE_CORS_ORIGINS",
    )
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sso: SsoConfig = Field(default_factory=SsoConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=_config_file_candidates()),
            file_secret_settings,
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def redacted_database_url(self) -> str:
        return _redact_url_secret(self.database_url)

    @property
    def redacted_redis_url(self) -> str:
        return _redact_url_secret(self.redis_url)

    @model_validator(mode="after")
    def validate_runtime_security(self) -> Settings:
        environment = self.environment.strip().lower()
        if environment in {"local", "dev", "development", "test"}:
            return self

        errors: list[str] = []
        if self.auth_dev_tokens_enabled:
            errors.append("auth_dev_tokens_enabled must be false outside local/test")
        if self.trusted_header_auth_enabled:
            errors.append("trusted_header_auth_enabled must be false outside local/test")
        secret_lower = self.secret_key.lower()
        if len(self.secret_key) < 32 or any(
            marker in secret_lower for marker in ("change-this", "change-me", "local-demo", "replace")
        ):
            errors.append("secret_key must be a real server secret with at least 32 characters")
        database_url = self.database_url.lower()
        if database_url.startswith("sqlite"):
            errors.append("database_url must point to PostgreSQL outside local/test")
        if any(marker in database_url for marker in ("change-me", "example", "replace")):
            errors.append("database_url must not contain placeholder credentials outside local/test")
        if errors:
            raise ValueError("; ".join(errors))
        return self


def _redact_url_secret(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    userinfo, host = rest.split("@", 1)
    if ":" not in userinfo:
        return f"{scheme}://{userinfo}@{host}"
    username, _password = userinfo.split(":", 1)
    return f"{scheme}://{username}:***@{host}"


def _config_file_candidates() -> list[Path]:
    explicit = os.getenv("IPRL_CAE_CONFIG_FILE")
    if explicit:
        return [Path(explicit)]
    return [
        Path("../config/iprl-cae.config.toml"),
        Path("config/iprl-cae.config.toml"),
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
