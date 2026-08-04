"""Deterministic mock media providers for CreatorOS."""

from __future__ import annotations

from creatoros.core import CreatorOSValidationError
from creatoros.domain import AssetType, GeneratedAsset, NarrationTrack, generate_id
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name},
        )
    return normalized_value


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class MockImageProvider(MockProviderBase):
    """Deterministic mock image provider."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="image",
            capabilities={ProviderCapability.IMAGE_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate_image(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return a deterministic generated image asset."""

        _validate_non_blank(prompt, field_name="prompt")
        return ProviderResult[GeneratedAsset](
            data=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://assets/image.png"),
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


class MockVideoProvider(MockProviderBase):
    """Deterministic mock video provider."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="video",
            capabilities={ProviderCapability.VIDEO_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate_video(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return a deterministic generated video asset."""

        _validate_non_blank(prompt, field_name="prompt")
        return ProviderResult[GeneratedAsset](
            data=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://assets/video.mp4"),
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


class MockVoiceProvider(MockProviderBase):
    """Deterministic mock voice provider."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="voice",
            capabilities={ProviderCapability.VOICE_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate_voice(
        self,
        text: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[NarrationTrack]:
        """Return a deterministic narration track."""

        _validate_non_blank(text, field_name="text")
        return ProviderResult[NarrationTrack](
            data=NarrationTrack(uri="mock://assets/narration.wav", duration_seconds=6.0),
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


__all__ = [
    "MockImageProvider",
    "MockVideoProvider",
    "MockVoiceProvider",
]
