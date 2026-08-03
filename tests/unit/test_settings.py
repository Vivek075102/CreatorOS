"""Unit tests for the CreatorOS settings module."""

import os
from unittest.mock import patch

from creatoros.config import get_settings
from creatoros.config.settings import Settings


def build_default_settings() -> Settings:
    """Create settings using only class defaults."""

    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None)


def test_default_app_name_is_creatoros() -> None:
    """The default application name should match the project name."""

    settings = build_default_settings()

    assert settings.app_name == "CreatorOS"


def test_default_provider_is_mock() -> None:
    """The default LLM provider should be the mock provider."""

    settings = build_default_settings()

    assert settings.default_llm_provider == "mock"


def test_database_url_uses_sqlite_by_default() -> None:
    """The default database URL should point to a sqlite database."""

    settings = build_default_settings()

    assert settings.database_url.startswith("sqlite")


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
