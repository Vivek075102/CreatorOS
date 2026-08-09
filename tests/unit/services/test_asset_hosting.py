"""Unit tests for the CreatorOS asset hosting service."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderNotFoundError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import create_provider_registry
from creatoros.providers.mock import MockAssetHostingProvider
from creatoros.services import AssetHostingService, create_asset_hosting_service


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in synchronous unit tests."""

    return asyncio.run(coro)


def build_settings(*, default_asset_hosting_provider: str = "mock") -> Settings:
    """Create isolated settings without reading the live environment."""

    project_root = Path("C:/GamingAIFactory")
    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider="mock",
        default_image_model=None,
        default_tts_provider="mock",
        default_tts_model=None,
        default_tts_voice="alloy",
        default_video_provider="mock",
        default_video_model=None,
        default_render_provider="mock",
        default_asset_hosting_provider=default_asset_hosting_provider,
        openai_api_key=None,
        cloudinary_cloud_name=None,
        cloudinary_api_key=None,
        cloudinary_api_secret=None,
        cloudinary_asset_folder="creatoros",
        kling_api_key=None,
        kling_api_base_url="https://api-singapore.klingai.com",
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        openai_image_timeout_seconds=300.0,
        kling_video_timeout_seconds=900.0,
        kling_video_poll_interval_seconds=5.0,
        provider_max_retries=3,
        ffmpeg_path=None,
        caption_font_name="Arial",
        caption_font_file=None,
        artifact_root=project_root / "artifacts",
        assets_dir=project_root / "assets",
        logs_dir=project_root / "logs",
        prompts_dir=project_root / "prompts",
    )


def build_asset() -> GeneratedAsset:
    """Create a provider-neutral generated image asset for hosting tests."""

    return GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri="C:/GamingAIFactory/artifacts/run_001/images/scene.png",
        metadata={"role": "scene_image"},
    )


def test_service_accepts_provider_registry_and_settings() -> None:
    """The service should accept valid dependencies."""

    service = AssetHostingService(create_provider_registry(), build_settings())

    assert isinstance(service, AssetHostingService)


def test_invalid_dependencies_are_rejected_safely() -> None:
    """Invalid service dependencies should fail with typed validation errors."""

    with pytest.raises(CreatorOSValidationError):
        AssetHostingService(object(), build_settings())  # type: ignore[arg-type]

    with pytest.raises(CreatorOSValidationError):
        AssetHostingService(create_provider_registry(), object())  # type: ignore[arg-type]


def test_default_provider_is_resolved_and_hosted_asset_is_returned() -> None:
    """Hosting should use the configured default provider and return the normalized asset."""

    registry = create_provider_registry()
    registry.register(MockAssetHostingProvider())
    service = AssetHostingService(registry, build_settings())

    result = run_async(service.host_asset(build_asset()))

    assert result.provider_name == "mock"
    assert result.public_url.startswith("https://example.invalid/")


def test_delete_defaults_to_hosted_asset_provider_name() -> None:
    """Delete should route back to the hosting provider recorded on the hosted asset."""

    registry = create_provider_registry()
    registry.register(MockAssetHostingProvider())
    service = AssetHostingService(registry, build_settings())
    hosted_asset = run_async(service.host_asset(build_asset()))

    deleted = run_async(service.delete_hosted_asset(hosted_asset))

    assert deleted is True


def test_unknown_provider_fails_safely() -> None:
    """Unknown hosting providers should raise the typed registry error."""

    service = create_asset_hosting_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(service.host_asset(build_asset(), provider_name="missing"))


def test_factory_builds_safe_mock_first_service() -> None:
    """The service factory should create a safe mock-first registry."""

    service = create_asset_hosting_service(settings=build_settings())

    assert service.provider_registry.contains("hosting", "mock") is True
