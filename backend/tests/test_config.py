from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


def test_runtime_toml_config_is_loaded_and_env_still_wins(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "iprl-cae.config.toml"
    config_file.write_text(
        """
app_name = "Configured Hub"
environment = "staging"
public_base_url = "https://api.example.test"
frontend_base_url = "https://app.example.test"
sso_state_ttl_minutes = 22
database_url = "postgresql+psycopg://iprl_cae:staging-password@localhost:5432/iprl_cae"
secret_key = "staging-secret-key-with-more-than-32-characters"

[sso]
enabled = true
default_provider = "google"
allowed_redirect_hosts = ["app.example.test"]

[sso.google]
enabled = true
allowed_domains = ["example.test"]
auto_provision_default = true

[connectors]
commercial_connectors_enabled = false
manual_export_enabled = true
rpa_enabled = false
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("IPRL_CAE_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("IPRL_CAE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("IPRL_CAE_APP_NAME", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Configured Hub"
    assert settings.environment == "staging"
    assert settings.public_base_url == "https://api.example.test"
    assert settings.sso_state_ttl_minutes == 22
    assert settings.sso.google.enabled is True
    assert settings.sso.google.allowed_domains == ["example.test"]
    assert settings.sso.google.auto_provision_default is True
    assert settings.connectors.manual_export_enabled is True
    assert settings.connectors.rpa_enabled is False

    monkeypatch.setenv("IPRL_CAE_APP_NAME", "Environment Hub")
    get_settings.cache_clear()

    assert get_settings().app_name == "Environment Hub"
    get_settings.cache_clear()


def test_server_runtime_rejects_demo_tokens_and_placeholder_secrets(
    monkeypatch,
) -> None:
    monkeypatch.delenv("IPRL_CAE_CONFIG_FILE", raising=False)
    monkeypatch.setenv("IPRL_CAE_ENVIRONMENT", "server")
    monkeypatch.setenv("IPRL_CAE_AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("IPRL_CAE_DATABASE_URL", "sqlite:///local.db")
    monkeypatch.setenv("IPRL_CAE_SECRET_KEY", "change-this-in-production-use-at-least-32-bytes")
    get_settings.cache_clear()

    try:
        try:
            get_settings()
        except ValueError as exc:
            message = str(exc)
            assert "auth_dev_tokens_enabled" in message
            assert "database_url must point to PostgreSQL" in message
            assert "secret_key must be a real server secret" in message
        else:
            raise AssertionError("Server settings accepted unsafe local/demo values.")
    finally:
        get_settings.cache_clear()


def test_versioned_config_does_not_contain_real_secret_values() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config" / "iprl-cae.config.toml"
    config_text = config_path.read_text(encoding="utf-8")

    assert "client_secret" in config_text
    assert "IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET" in config_text
    assert "change-this-in-production" not in config_text
    assert "BEGIN PRIVATE KEY" not in config_text
