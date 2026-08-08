"""Unit tests for the CreatorOS media render service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.config import Settings
from creatoros.core import ProviderNotFoundError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    GeneratedAudio,
    ProviderCapability,
    ProviderInfo,
    create_provider_registry,
)
from creatoros.providers.mock import MockRenderProvider
from creatoros.providers.render import RenderScene, ShortRenderRequest
from creatoros.services import MediaRenderService, create_media_render_service


def build_settings(*, default_render_provider: str = "mock") -> Settings:
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
        default_video_provider="mock",
        default_render_provider=default_render_provider,
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        assets_dir=project_root / "assets",
        logs_dir=project_root / "logs",
        prompts_dir=project_root / "prompts",
    )


def build_request() -> ShortRenderRequest:
    """Create a valid render request for service tests."""

    return ShortRenderRequest(
        scenes=[
            RenderScene(
                scene_number=1,
                duration_seconds=3.0,
                visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/1.png"),
            ),
            RenderScene(
                scene_number=2,
                duration_seconds=4.0,
                video_asset_ref=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://generated/video/2.mp4"),
            ),
        ],
        narration=GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=7.0,
        ),
    )


class RecordingRenderProvider(MockRenderProvider):
    """Simple render provider that records calls for service-forwarding tests."""

    def __init__(self, *, name: str = "mock") -> None:
        super().__init__()
        self._info = ProviderInfo(
            name=name,
            provider_type="render",
            capabilities={ProviderCapability.RENDERING},
        )
        self.calls = 0
        self.last_request: ShortRenderRequest | None = None

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def render(self, request: ShortRenderRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        return await super().render(request, context=context)


def test_service_uses_default_render_provider_from_settings() -> None:
    """The service should resolve the configured default render provider."""

    registry = create_provider_registry()
    provider = RecordingRenderProvider(name="mock")
    registry.register(provider)
    service = MediaRenderService(registry, build_settings(default_render_provider="mock"))

    result = asyncio.run(service.render(build_request()))

    assert result.data.provider_name == "mock"
    assert provider.calls == 1


def test_explicit_provider_name_overrides_default() -> None:
    """Explicit provider selection should override the configured default."""

    registry = create_provider_registry()
    default_provider = RecordingRenderProvider(name="mock")
    alternate_provider = RecordingRenderProvider(name="alternate")
    registry.register(default_provider)
    registry.register(alternate_provider)
    service = MediaRenderService(registry, build_settings(default_render_provider="mock"))

    result = asyncio.run(service.render(build_request(), provider_name="alternate"))

    assert result.data.provider_name == "alternate"
    assert default_provider.calls == 0
    assert alternate_provider.calls == 1


def test_unknown_render_provider_fails_safely() -> None:
    """Unknown render providers should raise the typed registry error."""

    service = create_media_render_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(service.render(build_request(), provider_name="missing"))


def test_factory_builds_mock_only_render_service() -> None:
    """The render-service factory should register the deterministic mock provider."""

    service = create_media_render_service(settings=build_settings())

    assert service.provider_registry.contains("render", "mock") is True
