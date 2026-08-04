"""Unit tests for the CreatorOS mock media providers."""

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.domain import AssetType
from creatoros.providers.mock import MockImageProvider, MockVideoProvider, MockVoiceProvider


def test_image_provider_returns_image_generated_asset() -> None:
    """Image generation should return a deterministic image asset."""

    provider = MockImageProvider()

    result = asyncio.run(provider.generate_image("generate image"))

    assert result.data.asset_type is AssetType.IMAGE
    assert result.data.uri == "mock://assets/image.png"


def test_video_provider_returns_video_generated_asset() -> None:
    """Video generation should return a deterministic video asset."""

    provider = MockVideoProvider()

    result = asyncio.run(provider.generate_video("generate video"))

    assert result.data.asset_type is AssetType.VIDEO
    assert result.data.uri == "mock://assets/video.mp4"


def test_voice_provider_returns_positive_duration_narration_track() -> None:
    """Voice generation should return a positive-duration narration track."""

    provider = MockVoiceProvider()

    result = asyncio.run(provider.generate_voice("generate narration"))

    assert result.data.duration_seconds > 0
    assert result.data.uri == "mock://assets/narration.wav"


def test_blank_prompts_or_text_are_rejected() -> None:
    """Blank media prompts and text should be rejected."""

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(MockImageProvider().generate_image("   "))

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(MockVideoProvider().generate_video("   "))

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(MockVoiceProvider().generate_voice("   "))
