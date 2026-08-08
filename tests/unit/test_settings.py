"""Unit tests for the CreatorOS settings module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from creatoros.config import get_settings
from creatoros.config.settings import PROJECT_ROOT, Settings


def build_settings(**overrides: object) -> Settings:
    """Create settings using only explicit overrides and class defaults."""

    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **overrides)


def test_default_app_name_is_creatoros() -> None:
    """The default application name should match the project name."""

    settings = build_settings()

    assert settings.app_name == "CreatorOS"


def test_default_environment_is_development() -> None:
    """The default application environment should be development."""

    settings = build_settings()

    assert settings.app_env == "development"


def test_default_provider_is_mock() -> None:
    """The default LLM provider should be the mock provider."""

    settings = build_settings()

    assert settings.default_llm_provider == "mock"


def test_default_media_providers_are_mock() -> None:
    """The default image, TTS, and video providers should use mock."""

    settings = build_settings()

    assert settings.default_image_provider == "mock"
    assert settings.default_tts_provider == "mock"
    assert settings.default_video_provider == "mock"
    assert settings.default_render_provider == "mock"


def test_default_image_model_is_unset() -> None:
    """The real image model should remain unset until explicitly configured."""

    settings = build_settings()

    assert settings.default_image_model is None


def test_default_tts_model_is_unset() -> None:
    """The real TTS model should remain unset until explicitly configured."""

    settings = build_settings()

    assert settings.default_tts_model is None


def test_default_database_url_uses_postgresql_psycopg() -> None:
    """The default database URL should use the PostgreSQL psycopg format."""

    settings = build_settings()

    assert settings.database_url.startswith("postgresql+psycopg")


def test_default_paths_resolve_to_project_root_directories() -> None:
    """Default asset, log, and prompt paths should point into the project root."""

    settings = build_settings()

    assert settings.artifact_root == PROJECT_ROOT / "artifacts"
    assert settings.assets_dir == PROJECT_ROOT / "assets"
    assert settings.logs_dir == PROJECT_ROOT / "logs"
    assert settings.prompts_dir == PROJECT_ROOT / "prompts"


def test_lowercase_log_levels_are_normalized_to_uppercase() -> None:
    """Lowercase log levels should be normalized during validation."""

    settings = build_settings(log_level="warning")

    assert settings.log_level == "WARNING"


def test_invalid_log_level_raises_validation_error() -> None:
    """Unsupported log levels should be rejected."""

    with pytest.raises(ValidationError):
        build_settings(log_level="verbose")


def test_blank_app_name_is_rejected() -> None:
    """Blank application names should not validate."""

    with pytest.raises(ValidationError):
        build_settings(app_name="   ")


def test_blank_database_url_is_rejected() -> None:
    """Blank database URLs should not validate."""

    with pytest.raises(ValidationError):
        build_settings(database_url="   ")


def test_negative_provider_timeout_is_rejected() -> None:
    """Provider timeouts must be positive."""

    with pytest.raises(ValidationError):
        build_settings(provider_timeout_seconds=-1.0)


def test_negative_provider_retry_count_is_rejected() -> None:
    """Provider retry counts must not be negative."""

    with pytest.raises(ValidationError):
        build_settings(provider_max_retries=-1)


@pytest.mark.parametrize(
    ("app_env", "property_name"),
    [
        ("development", "is_development"),
        ("testing", "is_testing"),
        ("production", "is_production"),
    ],
)
def test_environment_helper_properties_return_correct_values(
    app_env: str,
    property_name: str,
) -> None:
    """Environment helper properties should reflect the active application environment."""

    settings = build_settings(app_env=app_env)

    assert getattr(settings, property_name) is True


def test_environment_variables_override_defaults() -> None:
    """Environment variables should override default settings values."""

    with patch.dict(
        os.environ,
        {
            "APP_NAME": "CreatorOS Override",
            "APP_ENV": "testing",
            "LOG_LEVEL": "error",
            "DATABASE_URL": "postgresql+psycopg://override_user:change_me@localhost:5432/creatoros_test",
            "DEFAULT_LLM_PROVIDER": "anthropic",
            "DEFAULT_IMAGE_PROVIDER": "custom-image",
            "DEFAULT_IMAGE_MODEL": "gpt-image-1",
            "DEFAULT_TTS_PROVIDER": "custom-tts",
            "DEFAULT_TTS_MODEL": "gpt-4o-mini-tts",
            "DEFAULT_VIDEO_PROVIDER": "custom-video",
            "DEFAULT_RENDER_PROVIDER": "custom-render",
            "PROVIDER_TIMEOUT_SECONDS": "45",
            "PROVIDER_MAX_RETRIES": "5",
            "ARTIFACT_ROOT": "runtime_artifacts",
            "ASSETS_DIR": "custom_assets",
            "LOGS_DIR": "custom_logs",
            "PROMPTS_DIR": "custom_prompts",
        },
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.app_name == "CreatorOS Override"
    assert settings.app_env == "testing"
    assert settings.log_level == "ERROR"
    assert settings.database_url.startswith("postgresql+psycopg://override_user")
    assert settings.default_llm_provider == "anthropic"
    assert settings.default_image_provider == "custom-image"
    assert settings.default_image_model == "gpt-image-1"
    assert settings.default_tts_provider == "custom-tts"
    assert settings.default_tts_model == "gpt-4o-mini-tts"
    assert settings.default_video_provider == "custom-video"
    assert settings.default_render_provider == "custom-render"
    assert settings.provider_timeout_seconds == 45.0
    assert settings.provider_max_retries == 5
    assert settings.artifact_root == PROJECT_ROOT / Path("runtime_artifacts")
    assert settings.assets_dir == PROJECT_ROOT / Path("custom_assets")
    assert settings.logs_dir == PROJECT_ROOT / Path("custom_logs")
    assert settings.prompts_dir == PROJECT_ROOT / Path("custom_prompts")


def test_get_settings_returns_cached_instance() -> None:
    """Repeated calls should return the same cached settings instance."""

    get_settings.cache_clear()

    with patch("creatoros.config.settings.Settings", autospec=True) as mock_settings:
        sentinel = object()
        mock_settings.return_value = sentinel

        first = get_settings()
        second = get_settings()

    assert first is second
    mock_settings.assert_called_once_with()
