"""Unit tests for the CreatorOS mock media providers."""

import asyncio
from pathlib import Path

import pytest

from creatoros.domain import AssetType
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    ImageProvider,
    TTSGenerationRequest,
    TTSProvider,
    VideoGenerationRequest,
    VideoProvider,
)
from creatoros.providers.mock import (
    MockImageProvider,
    MockTTSProvider,
    MockVideoProvider,
    MockVoiceProvider,
)


def test_image_provider_returns_image_generated_asset() -> None:
    """Image generation should return a deterministic typed image result."""

    provider = MockImageProvider()

    result = asyncio.run(provider.generate(ImageGenerationRequest(prompt="generate image")))

    assert isinstance(result.data, GeneratedImage)
    assert result.data.artifact.asset_type is AssetType.IMAGE
    assert result.data.artifact.uri.startswith("mock://generated/image/")


def test_video_provider_returns_video_generated_asset() -> None:
    """Video generation should return a deterministic typed video result."""

    provider = MockVideoProvider()

    result = asyncio.run(
        provider.generate(VideoGenerationRequest(prompt="generate video", duration_seconds=4.0))
    )

    assert isinstance(result.data, GeneratedVideo)
    assert result.data.artifact.asset_type is AssetType.VIDEO
    assert result.data.artifact.uri.startswith("mock://generated/video/")


def test_tts_provider_returns_generated_audio() -> None:
    """TTS generation should return a deterministic typed audio result."""

    provider = MockTTSProvider()

    result = asyncio.run(provider.generate(TTSGenerationRequest(text="generate narration")))

    assert isinstance(result.data, GeneratedAudio)
    assert result.data.artifact.asset_type is AssetType.AUDIO
    assert result.data.artifact.uri.startswith("mock://generated/audio/")
    assert result.data.estimated_duration_seconds is not None


def test_voice_provider_compatibility_path_returns_positive_duration_narration_track() -> None:
    """Legacy voice generation should remain available for the demo workflow."""

    provider = MockVoiceProvider()

    result = asyncio.run(provider.generate_voice("generate narration"))

    assert result.data.duration_seconds > 0
    assert result.data.uri.startswith("mock://generated/audio/")


def test_blank_prompts_or_text_are_rejected() -> None:
    """Blank media prompts and text should be rejected."""

    with pytest.raises(ValueError):
        ImageGenerationRequest(prompt="   ")

    with pytest.raises(ValueError):
        VideoGenerationRequest(prompt="   ", duration_seconds=4.0)

    with pytest.raises(ValueError):
        TTSGenerationRequest(text="   ")


def test_same_input_produces_predictable_media_artifact_identities() -> None:
    """Identical typed inputs should produce identical mock artifact references."""

    image_provider = MockImageProvider()
    first_image = asyncio.run(image_provider.generate(ImageGenerationRequest(prompt="same prompt")))
    second_image = asyncio.run(image_provider.generate(ImageGenerationRequest(prompt="same prompt")))

    tts_provider = MockTTSProvider()
    first_audio = asyncio.run(tts_provider.generate(TTSGenerationRequest(text="same line")))
    second_audio = asyncio.run(tts_provider.generate(TTSGenerationRequest(text="same line")))

    video_provider = MockVideoProvider()
    first_video = asyncio.run(
        video_provider.generate(VideoGenerationRequest(prompt="same shot", duration_seconds=4.0))
    )
    second_video = asyncio.run(
        video_provider.generate(VideoGenerationRequest(prompt="same shot", duration_seconds=4.0))
    )

    assert first_image.data.artifact.uri == second_image.data.artifact.uri
    assert first_audio.data.artifact.uri == second_audio.data.artifact.uri
    assert first_video.data.artifact.uri == second_video.data.artifact.uri


def test_mock_media_providers_satisfy_runtime_protocols() -> None:
    """Mock media providers should satisfy the declared runtime protocols."""

    assert isinstance(MockImageProvider(), ImageProvider)
    assert isinstance(MockTTSProvider(), TTSProvider)
    assert isinstance(MockVideoProvider(), VideoProvider)


def test_mock_media_generation_creates_no_local_files(tmp_path: Path) -> None:
    """Mock media providers should not create local files while generating results."""

    before = tuple(tmp_path.iterdir())

    asyncio.run(MockImageProvider().generate(ImageGenerationRequest(prompt="still no file")))
    asyncio.run(MockTTSProvider().generate(TTSGenerationRequest(text="still no file")))
    asyncio.run(
        MockVideoProvider().generate(
            VideoGenerationRequest(prompt="still no file", duration_seconds=4.0)
        )
    )

    assert tuple(tmp_path.iterdir()) == before


def test_mock_media_module_contains_no_network_or_ffmpeg_usage() -> None:
    """The mock media provider module should stay offline and avoid rendering tools."""

    module_source = Path("creatoros/providers/mock/media.py").read_text(encoding="utf-8")

    assert "httpx" not in module_source
    assert "requests" not in module_source
    assert "subprocess" not in module_source
