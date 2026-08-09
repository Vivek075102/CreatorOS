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
    build_audio_filter_chain,
    build_audio_render_plan,
    build_narration_filter_chain,
)
from creatoros.providers.media import GeneratedAudio
from creatoros.providers.render import (
    AudioCompositionPolicy,
    AudioLoopPolicy,
    AudioTrack,
    AudioTrackRole,
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
    assert plan.tracks == ()


def test_audio_render_plan_normalizes_to_aac_48khz_stereo() -> None:
    """Narration should normalize into one deterministic output audio configuration."""

    plan = build_audio_render_plan(build_request())

    assert plan.include_audio_stream is True
    assert plan.codec == DEFAULT_OUTPUT_AUDIO_CODEC
    assert plan.sample_rate_hz == DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ
    assert plan.channel_layout == DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT
    assert plan.bitrate == DEFAULT_OUTPUT_AUDIO_BITRATE
    assert len(plan.tracks) == 1
    assert plan.tracks[0].role is AudioTrackRole.NARRATION


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
    assert plan.tracks[0].source_duration_seconds is None


def test_background_music_track_is_supported_with_ducking_intent() -> None:
    """Background music should remain provider-neutral while carrying ducking intent."""

    request = build_request(include_narration=False).model_copy(
        update={
            "audio_tracks": (
                AudioTrack(
                    source_asset_ref=GeneratedAsset(
                        asset_type=AssetType.AUDIO,
                        uri="mock://generated/audio/music.wav",
                    ),
                    role=AudioTrackRole.BACKGROUND_MUSIC,
                    source_duration_seconds=3.0,
                    gain_db=-18.0,
                    fade_in_seconds=0.5,
                    fade_out_seconds=0.75,
                    loop_policy=AudioLoopPolicy.LOOP_TO_FIT,
                    duck_under_narration=True,
                ),
            )
        }
    )

    plan = build_audio_render_plan(request)

    assert plan.include_audio_stream is True
    assert len(plan.tracks) == 1
    assert plan.tracks[0].role is AudioTrackRole.BACKGROUND_MUSIC
    assert plan.tracks[0].duck_under_narration is True
    assert plan.tracks[0].loop_policy is AudioLoopPolicy.LOOP_TO_FIT


def test_sound_effect_tracks_are_supported_with_explicit_start_times() -> None:
    """Sound effects should remain ordered and timeline-positioned."""

    request = build_request(include_narration=False).model_copy(
        update={
            "audio_tracks": (
                AudioTrack(
                    source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/sfx1.wav"),
                    role=AudioTrackRole.SOUND_EFFECT,
                    start_seconds=0.25,
                    source_duration_seconds=0.5,
                ),
                AudioTrack(
                    source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/sfx2.wav"),
                    role=AudioTrackRole.SOUND_EFFECT,
                    start_seconds=1.5,
                    source_duration_seconds=0.25,
                    gain_db=-6.0,
                ),
            )
        }
    )

    plan = build_audio_render_plan(request)

    assert [track.role for track in plan.tracks] == [
        AudioTrackRole.SOUND_EFFECT,
        AudioTrackRole.SOUND_EFFECT,
    ]
    assert [track.start_seconds for track in plan.tracks] == [0.25, 1.5]


def test_negative_audio_start_time_is_rejected() -> None:
    """Negative audio start positions should fail validation."""

    with pytest.raises(ValidationError):
        AudioTrack(
            source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/sfx.wav"),
            role=AudioTrackRole.SOUND_EFFECT,
            start_seconds=-0.1,
        )


def test_invalid_gain_and_fade_are_rejected() -> None:
    """Out-of-range gain and impossible fade combinations should fail clearly."""

    with pytest.raises(ValidationError):
        AudioTrack(
            source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/music.wav"),
            role=AudioTrackRole.BACKGROUND_MUSIC,
            source_duration_seconds=1.0,
            gain_db=-80.0,
        )

    with pytest.raises(ValidationError):
        AudioTrack(
            source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/music.wav"),
            role=AudioTrackRole.BACKGROUND_MUSIC,
            source_duration_seconds=1.0,
            fade_in_seconds=0.75,
            fade_out_seconds=0.5,
        )


def test_audio_filter_chain_supports_narration_music_and_sfx() -> None:
    """The pure filter builder should mix narration, music, and SFX deterministically."""

    request = build_request().model_copy(
        update={
            "audio_tracks": (
                AudioTrack(
                    source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/music.wav"),
                    role=AudioTrackRole.BACKGROUND_MUSIC,
                    source_duration_seconds=2.0,
                    gain_db=-18.0,
                    fade_in_seconds=0.5,
                    fade_out_seconds=0.5,
                    loop_policy=AudioLoopPolicy.LOOP_TO_FIT,
                    duck_under_narration=True,
                ),
                AudioTrack(
                    source_asset_ref=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/whoosh.wav"),
                    role=AudioTrackRole.SOUND_EFFECT,
                    start_seconds=1.0,
                    source_duration_seconds=0.25,
                    gain_db=-3.0,
                ),
            )
        }
    )
    plan = build_audio_render_plan(request)

    filter_chain = build_audio_filter_chain(
        plan=plan,
        target_duration_seconds=request.total_duration_seconds,
        input_stream_indexes=(1, 2, 3),
        audio_policy=request.audio_policy,
        production_timeline=request.production_timeline,
    )

    assert "[1:a]" in filter_chain
    assert "[2:a]" in filter_chain
    assert "[3:a]" in filter_chain
    assert "amix=inputs=3" in filter_chain
    assert "afade=t=in:st=0:d=0.5" in filter_chain
    assert "afade=t=out" in filter_chain
    assert "adelay=1000|1000" in filter_chain
    assert "if(gt(" in filter_chain
    assert "[audio_out]" in filter_chain
