"""Unit tests for provider-neutral media-generation contracts."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    TTSGenerationRequest,
    VideoGenerationRequest,
)


def test_image_request_normalizes_prompt() -> None:
    """Image requests should trim prompt text."""

    request = ImageGenerationRequest(prompt="  hero frame  ")

    assert request.prompt == "hero frame"


def test_blank_image_prompt_is_rejected() -> None:
    """Image requests should reject blank prompts."""

    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="   ")


def test_invalid_image_dimensions_are_rejected() -> None:
    """Image requests should require positive dimensions."""

    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="hero", width=0)

    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="hero", height=0)


def test_tts_request_normalizes_text() -> None:
    """TTS requests should trim narration text."""

    request = TTSGenerationRequest(text="  hello there  ", voice="  calm  ", language="  en  ")

    assert request.text == "hello there"
    assert request.voice == "calm"
    assert request.language == "en"


def test_blank_tts_text_is_rejected() -> None:
    """TTS requests should reject blank narration text."""

    with pytest.raises(ValidationError):
        TTSGenerationRequest(text="   ")


def test_invalid_tts_numeric_fields_are_rejected() -> None:
    """TTS requests should require positive finite numeric fields."""

    with pytest.raises(ValidationError):
        TTSGenerationRequest(text="hello", speed=0)

    with pytest.raises(ValidationError):
        TTSGenerationRequest(text="hello", speed=math.inf)


def test_video_request_normalizes_prompt() -> None:
    """Video requests should trim prompt text."""

    request = VideoGenerationRequest(prompt="  opener shot  ", duration_seconds=3.5)

    assert request.prompt == "opener shot"


def test_video_request_accepts_provider_neutral_reference_image() -> None:
    """Video requests should accept a generated image asset as a reference image."""

    reference_image = GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri="mock://generated/image/reference.png",
        metadata={"role": "reference"},
    )

    request = VideoGenerationRequest(
        prompt="Animate this keyframe",
        duration_seconds=3.5,
        reference_image=reference_image,
    )

    assert request.reference_image is not None
    assert request.reference_image.asset_type is AssetType.IMAGE
    assert request.reference_image.uri == "mock://generated/image/reference.png"


def test_video_request_copies_reference_image_safely_without_mutating_source() -> None:
    """Reference image assets should be deep-copied defensively."""

    reference_image = GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri="mock://generated/image/reference.png",
        metadata={"tag": "original"},
    )
    request = VideoGenerationRequest(
        prompt="Animate this still",
        duration_seconds=4.0,
        reference_image=reference_image,
    )

    reference_image.uri = "mock://generated/image/mutated.png"
    reference_image.metadata["tag"] = "mutated"

    assert request.reference_image is not None
    assert request.reference_image.uri == "mock://generated/image/reference.png"
    assert request.reference_image.metadata["tag"] == "original"


def test_video_request_rejects_non_image_reference_assets() -> None:
    """Image-to-video references should stay constrained to image assets."""

    with pytest.raises(ValidationError):
        VideoGenerationRequest(
            prompt="Animate this clip",
            duration_seconds=4.0,
            reference_image=GeneratedAsset(
                asset_type=AssetType.VIDEO,
                uri="mock://generated/video/not-an-image.mp4",
            ),
        )


def test_video_request_serialization_excludes_any_binary_payload_fields() -> None:
    """Reference-image contracts should remain lightweight and metadata-safe."""

    request = VideoGenerationRequest(
        prompt="Animate this still",
        duration_seconds=4.0,
        reference_image=GeneratedAsset(
            asset_type=AssetType.IMAGE,
            uri="mock://generated/image/reference.png",
            metadata={"hint": "safe"},
        ),
    )
    dumped = request.model_dump()

    assert dumped["reference_image"]["uri"] == "mock://generated/image/reference.png"
    assert "payload_bytes" not in str(dumped)


def test_blank_video_prompt_is_rejected() -> None:
    """Video requests should reject blank prompts."""

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="   ", duration_seconds=3.5)


def test_non_positive_video_duration_is_rejected() -> None:
    """Video requests should require positive durations."""

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="opener", duration_seconds=0)


def test_invalid_video_dimensions_and_fps_are_rejected() -> None:
    """Video requests should require positive finite dimensions and frame rates."""

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="opener", duration_seconds=3.5, width=0)

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="opener", duration_seconds=3.5, height=0)

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="opener", duration_seconds=3.5, fps=0)

    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="opener", duration_seconds=3.5, fps=math.inf)


def test_generated_image_result_validates() -> None:
    """Generated image results should accept valid provider-neutral metadata."""

    result = GeneratedImage(
        artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/frame.png"),
        provider_name="mock",
        model="mock-image-model",
        mime_type="image/png",
        width=1024,
        height=1024,
    )

    assert result.provider_name == "mock"


def test_generated_audio_result_validates() -> None:
    """Generated audio results should accept valid provider-neutral metadata."""

    result = GeneratedAudio(
        artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/voice.wav"),
        provider_name="mock",
        model="mock-tts-model",
        mime_type="audio/wav",
        estimated_duration_seconds=5.0,
    )

    assert result.mime_type == "audio/wav"


def test_generated_video_result_validates() -> None:
    """Generated video results should accept valid provider-neutral metadata."""

    result = GeneratedVideo(
        artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://generated/video/clip.mp4"),
        provider_name="mock",
        model="mock-video-model",
        mime_type="video/mp4",
        duration_seconds=4.0,
    )

    assert result.duration_seconds == 4.0


def test_media_result_metadata_defaults_are_isolated() -> None:
    """Media result metadata dictionaries should not be shared."""

    first = GeneratedImage(
        artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/one.png"),
        provider_name="mock",
        model="mock-image-model",
        mime_type="image/png",
        width=1024,
        height=1024,
    )
    second = GeneratedImage(
        artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/two.png"),
        provider_name="mock",
        model="mock-image-model",
        mime_type="image/png",
        width=1024,
        height=1024,
    )

    first.metadata["tag"] = "one"

    assert second.metadata == {}


def test_blank_provider_identity_is_rejected_for_media_results() -> None:
    """Media results should reject blank provider identity fields."""

    with pytest.raises(ValidationError):
        GeneratedImage(
            artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/frame.png"),
            provider_name="   ",
            model="mock-image-model",
            mime_type="image/png",
            width=1024,
            height=1024,
        )


def test_video_request_contract_remains_provider_neutral() -> None:
    """The video request contract should not grow Kling-specific or raw-path fields."""

    source = Path("creatoros/providers/media.py").read_text(encoding="utf-8")

    assert "reference_image" in source
    assert "image_path" not in source
    assert "kling_" not in source
