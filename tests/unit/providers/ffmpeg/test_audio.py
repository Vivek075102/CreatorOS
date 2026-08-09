"""Unit tests for pure FFmpeg audio composition helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers.ffmpeg.audio import (
    DEFAULT_OUTPUT_AUDIO_BITRATE,
    DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
    DEFAULT_OUTPUT_AUDIO_CODEC,
    DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
    build_audio_render_plan,
    build_narration_filter_chain,
)
from creatoros.providers.media import GeneratedAudio
from creatoros.providers.render import (
    AudioCompositionPolicy,
    NarrationTimingPolicy,
    RenderScene,
    ShortRenderRequest,
)


def build_request(*, include_narration: bool = True, narration_duration: float | None = 2.0) -> ShortRenderRequest:
    """Create one render request for pure audio composition tests."""

    narration = None
    if include_narration:
        narration = GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=narration_duration,
        )

    return ShortRenderRequest(
        scenes=[
            RenderScene(
                scene_number=1,
                duration_seconds=2.0,
                visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene1.png"),
            ),
            RenderScene(
                scene_number=2,
                duration_seconds=3.0,
                visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene2.png"),
            ),
        ],
        narration=narration,
    )


def test_default_audio_policy_is_deterministic() -> None:
    """The default audio policy should use the only supported narration timing mode."""

    request = build_request()

    assert request.audio_policy == AudioCompositionPolicy(
        narration_timing=NarrationTimingPolicy.FIT_TO_VIDEO,
    )


def test_invalid_audio_policy_is_rejected() -> None:
    """Invalid narration timing values should fail model validation."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(
            scenes=[
                RenderScene(
                    scene_number=1,
                    duration_seconds=2.0,
                    visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene1.png"),
                )
            ],
            audio_policy={"narration_timing": "loop_forever"},
        )


def test_audio_render_plan_uses_no_audio_stream_without_narration() -> None:
    """No narration should keep the simplest no-audio final output path."""

    plan = build_audio_render_plan(build_request(include_narration=False))

    assert plan.include_audio_stream is False
    assert plan.filter_chain is None


def test_audio_render_plan_normalizes_to_aac_48khz_stereo() -> None:
    """Narration should normalize into one deterministic output audio configuration."""

    plan = build_audio_render_plan(build_request())

    assert plan.include_audio_stream is True
    assert plan.codec == DEFAULT_OUTPUT_AUDIO_CODEC
    assert plan.sample_rate_hz == DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ
    assert plan.channel_layout == DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT
    assert plan.bitrate == DEFAULT_OUTPUT_AUDIO_BITRATE


def test_narration_filter_chain_pads_and_trims_to_video_duration() -> None:
    """The audio filter chain should fit narration to the video timeline exactly."""

    assert build_narration_filter_chain(target_duration_seconds=5.0) == (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration=5[narration_out]"
    )


def test_unknown_narration_duration_metadata_is_accepted_without_fabrication() -> None:
    """Missing narration duration estimates should not block the bounded audio plan."""

    request = build_request(narration_duration=None)
    plan = build_audio_render_plan(request)

    assert request.narration is not None
    assert request.narration.estimated_duration_seconds is None
    assert plan.include_audio_stream is True
    assert plan.filter_chain is not None
