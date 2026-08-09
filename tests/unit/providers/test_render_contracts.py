"""Unit tests for CreatorOS render and composition contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    CaptionOverlay,
    CaptionPosition,
    GeneratedAudio,
    RenderedVideo,
    RenderScene,
    RenderTransition,
    ShortRenderRequest,
)


def build_image_asset(uri: str = "mock://generated/image/scene.png") -> GeneratedAsset:
    """Create a reusable image asset reference."""

    return GeneratedAsset(asset_type=AssetType.IMAGE, uri=uri)


def build_video_asset(uri: str = "mock://generated/video/scene.mp4") -> GeneratedAsset:
    """Create a reusable video asset reference."""

    return GeneratedAsset(asset_type=AssetType.VIDEO, uri=uri)


def build_audio(*, duration: float | None = None) -> GeneratedAudio:
    """Create a reusable narration reference."""

    return GeneratedAudio(
        artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
        provider_name="mock",
        model="mock-tts-model",
        mime_type="audio/wav",
        estimated_duration_seconds=duration,
    )


def build_scene(
    *,
    scene_number: int = 1,
    duration_seconds: float = 3.0,
    caption_text: str | None = " Caption text ",
) -> RenderScene:
    """Create a valid render scene for focused tests."""

    return RenderScene(
        scene_number=scene_number,
        duration_seconds=duration_seconds,
        visual_asset_ref=build_image_asset(f"mock://generated/image/{scene_number}.png"),
        caption_text=caption_text,
        motion_instruction=" Slow push in ",
        transition=RenderTransition.CUT,
    )


def test_valid_render_scene_is_accepted() -> None:
    """A valid render scene should normalize optional planning text."""

    scene = build_scene()

    assert scene.caption == CaptionOverlay(text="Caption text")
    assert scene.caption_text == "Caption text"
    assert scene.motion_instruction == "Slow push in"


def test_scene_number_must_be_positive() -> None:
    """Scene numbers must be greater than zero."""

    with pytest.raises(ValidationError):
        build_scene(scene_number=0)


def test_scene_duration_must_be_positive() -> None:
    """Scene durations must be positive."""

    with pytest.raises(ValidationError):
        build_scene(duration_seconds=0.0)


def test_scene_requires_at_least_one_asset_reference() -> None:
    """Scenes must carry either an image or video asset reference."""

    with pytest.raises(ValidationError):
        RenderScene(scene_number=1, duration_seconds=3.0)


def test_blank_explicit_caption_is_rejected() -> None:
    """Explicit caption overlays should reject blank text."""

    with pytest.raises(ValidationError):
        RenderScene(
            scene_number=1,
            duration_seconds=3.0,
            visual_asset_ref=build_image_asset(),
            caption={"text": "   "},
        )


def test_invalid_caption_position_is_rejected() -> None:
    """Caption positions should stay within the provider-neutral enum."""

    with pytest.raises(ValidationError):
        RenderScene(
            scene_number=1,
            duration_seconds=3.0,
            visual_asset_ref=build_image_asset(),
            caption={"text": "Caption text", "position": "left"},
        )


def test_unicode_caption_serialization_is_deterministic() -> None:
    """Caption overlays should serialize deterministically with Unicode text."""

    scene = RenderScene(
        scene_number=1,
        duration_seconds=3.0,
        visual_asset_ref=build_image_asset(),
        caption=CaptionOverlay(text="Unicode myth π", position=CaptionPosition.TOP),
    )

    first_dump = scene.model_dump(mode="json")
    second_dump = scene.model_dump(mode="json")

    assert first_dump == second_dump
    assert first_dump["caption"]["text"] == "Unicode myth π"


def test_scene_rejects_wrong_asset_types() -> None:
    """Scene asset slots must preserve image versus video semantics."""

    with pytest.raises(ValidationError):
        RenderScene(
            scene_number=1,
            duration_seconds=3.0,
            visual_asset_ref=build_video_asset(),
        )


def test_valid_short_render_request_is_accepted() -> None:
    """A valid request should compute deterministic total duration."""

    request = ShortRenderRequest(
        scenes=[build_scene(scene_number=1, duration_seconds=3.0), build_scene(scene_number=2, duration_seconds=4.5)],
        narration=build_audio(duration=7.0),
    )

    assert request.total_duration_seconds == 7.5


def test_request_requires_at_least_one_scene() -> None:
    """Render requests must include at least one scene."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(scenes=[])


def test_request_requires_sequential_scene_numbers() -> None:
    """Skipped or reordered scene numbers should be rejected."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(scenes=[build_scene(scene_number=1), build_scene(scene_number=3)])


def test_request_rejects_invalid_dimensions_or_fps() -> None:
    """Dimensions and frame rate must stay positive."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(scenes=[build_scene()], width=0)

    with pytest.raises(ValidationError):
        ShortRenderRequest(scenes=[build_scene()], fps=0.0)


def test_request_mutable_defaults_are_isolated() -> None:
    """Metadata should not leak between render requests."""

    first = ShortRenderRequest(scenes=[build_scene()], metadata={"tags": ["safe"]})
    second = ShortRenderRequest(scenes=[build_scene(scene_number=1, duration_seconds=2.0)])

    first.metadata["tags"].append("mutated")

    assert second.metadata == {}


def test_narration_duration_may_be_absent_without_fabrication() -> None:
    """Missing narration duration should remain unset and still validate."""

    request = ShortRenderRequest(scenes=[build_scene()], narration=build_audio(duration=None))

    assert request.narration is not None
    assert request.narration.estimated_duration_seconds is None


def test_narration_duration_cannot_exceed_scene_duration_by_large_margin() -> None:
    """Known narration duration should remain within the documented tolerance."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(scenes=[build_scene(duration_seconds=3.0)], narration=build_audio(duration=4.5))


def test_valid_rendered_video_is_accepted() -> None:
    """A valid rendered video should preserve normalized values."""

    result = RenderedVideo(
        artifact=build_video_asset("mock://rendered/video/final.mp4"),
        provider_name=" mock ",
        mime_type=" video/mp4 ",
        duration_seconds=7.5,
        width=1080,
        height=1920,
        fps=30.0,
        metadata={"scene_count": 2},
    )

    assert result.provider_name == "mock"
    assert result.mime_type == "video/mp4"


def test_rendered_video_rejects_blank_provider_identity() -> None:
    """Rendered results should reject blank provider names."""

    with pytest.raises(ValidationError):
        RenderedVideo(
            artifact=build_video_asset(),
            provider_name="   ",
            mime_type="video/mp4",
            duration_seconds=2.0,
            width=1080,
            height=1920,
            fps=30.0,
        )


def test_rendered_video_metadata_is_isolated() -> None:
    """Result metadata should not leak across instances."""

    first = RenderedVideo(
        artifact=build_video_asset("mock://rendered/video/one.mp4"),
        provider_name="mock",
        mime_type="video/mp4",
        duration_seconds=2.0,
        width=1080,
        height=1920,
        fps=30.0,
        metadata={"tags": ["safe"]},
    )
    second = RenderedVideo(
        artifact=build_video_asset("mock://rendered/video/two.mp4"),
        provider_name="mock",
        mime_type="video/mp4",
        duration_seconds=2.0,
        width=1080,
        height=1920,
        fps=30.0,
    )

    first.metadata["tags"].append("mutated")

    assert second.metadata == {}
