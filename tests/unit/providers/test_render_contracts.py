"""Unit tests for CreatorOS render and composition contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    DEFAULT_CROSSFADE_DURATION_SECONDS,
    AudioCompositionPolicy,
    CaptionOverlay,
    CaptionPosition,
    GeneratedAudio,
    NarrationTimingPolicy,
    ProductionTimeline,
    ProductionTimelineScene,
    RenderedVideo,
    RenderScene,
    RenderTransition,
    SceneVisualTreatment,
    ShortRenderRequest,
    VisualMotion,
    VisualMotionIntensity,
    build_default_visual_treatment,
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


def build_timeline(
    *,
    durations: tuple[float, ...] = (3.0,),
    assets: tuple[GeneratedAsset, ...] | None = None,
) -> ProductionTimeline:
    """Create a reusable production timeline for render-contract tests."""

    resolved_assets = (
        tuple(build_image_asset(f"mock://generated/image/{index}.png") for index in range(1, len(durations) + 1))
        if assets is None
        else assets
    )
    scenes: list[ProductionTimelineScene] = []
    current_start = 0.0
    for index, duration in enumerate(durations, start=1):
        current_end = round(current_start + duration, 6)
        scenes.append(
            ProductionTimelineScene(
                scene_number=index,
                start_seconds=current_start,
                end_seconds=current_end,
                duration_seconds=duration,
                source_asset_ref=resolved_assets[index - 1],
                caption_text=f"Caption {index}",
            )
        )
        current_start = current_end
    return ProductionTimeline(scenes=scenes, target_duration_seconds=sum(durations))


def test_valid_render_scene_is_accepted() -> None:
    """A valid render scene should normalize optional planning text."""

    scene = build_scene()

    assert scene.caption == CaptionOverlay(text="Caption text")
    assert scene.caption_text == "Caption text"
    assert scene.motion_instruction == "Slow push in"
    assert scene.transition is RenderTransition.CUT


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


def test_visual_treatment_defaults_are_valid() -> None:
    """The provider-neutral visual-treatment model should expose safe defaults."""

    treatment = SceneVisualTreatment()

    assert treatment.motion is VisualMotion.NONE
    assert treatment.intensity is VisualMotionIntensity.SUBTLE
    assert treatment.transition is RenderTransition.CUT
    assert treatment.transition_duration_seconds == 0.0


def test_unsupported_motion_is_rejected() -> None:
    """Only the provider-neutral motion enum should be accepted."""

    with pytest.raises(ValidationError):
        SceneVisualTreatment(motion="spiral")


def test_unsupported_transition_is_rejected() -> None:
    """Only the provider-neutral transition enum should be accepted."""

    with pytest.raises(ValidationError):
        SceneVisualTreatment(transition="wipe")


def test_legacy_fade_transition_normalizes_to_crossfade() -> None:
    """Legacy fade transition names should normalize to crossfade safely."""

    scene = RenderScene(
        scene_number=1,
        duration_seconds=3.0,
        visual_asset_ref=build_image_asset(),
        transition="fade",
    )

    assert scene.transition is RenderTransition.CROSSFADE


def test_default_visual_treatment_is_deterministic_for_still_images() -> None:
    """Still-image scenes should receive a deterministic motion-and-transition pattern."""

    first = build_default_visual_treatment(
        scene_number=1,
        source_asset_type=AssetType.IMAGE,
        next_source_asset_type=AssetType.IMAGE,
    )
    second = build_default_visual_treatment(
        scene_number=2,
        source_asset_type=AssetType.IMAGE,
        next_source_asset_type=AssetType.IMAGE,
    )
    repeat = build_default_visual_treatment(
        scene_number=1,
        source_asset_type=AssetType.IMAGE,
        next_source_asset_type=AssetType.IMAGE,
    )

    assert first.motion is VisualMotion.PUSH_IN
    assert second.motion is VisualMotion.PAN_RIGHT
    assert first.transition is RenderTransition.CROSSFADE
    assert first.transition_duration_seconds == DEFAULT_CROSSFADE_DURATION_SECONDS
    assert first == repeat


def test_default_visual_treatment_preserves_native_video_motion() -> None:
    """Generated-video scenes should default to no synthetic camera motion."""

    treatment = build_default_visual_treatment(
        scene_number=3,
        source_asset_type=AssetType.VIDEO,
        next_source_asset_type=AssetType.VIDEO,
    )

    assert treatment.motion is VisualMotion.NONE
    assert treatment.transition is RenderTransition.CUT


def test_crossfade_requires_non_final_following_scene_and_safe_duration() -> None:
    """Timeline validation should bound crossfade duration safely."""

    with pytest.raises(ValidationError):
        ProductionTimeline(
            scenes=[
                ProductionTimelineScene(
                    scene_number=1,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    duration_seconds=1.0,
                    source_asset_ref=build_image_asset("mock://generated/image/1.png"),
                    visual_treatment=SceneVisualTreatment(
                        transition=RenderTransition.CROSSFADE,
                        transition_duration_seconds=1.0,
                    ),
                ),
                ProductionTimelineScene(
                    scene_number=2,
                    start_seconds=1.0,
                    end_seconds=2.0,
                    duration_seconds=1.0,
                    source_asset_ref=build_image_asset("mock://generated/image/2.png"),
                ),
            ],
            target_duration_seconds=2.0,
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
        production_timeline=build_timeline(durations=(3.0, 4.5)),
        narration=build_audio(duration=7.0),
    )

    assert request.total_duration_seconds == 7.5
    assert request.audio_policy == AudioCompositionPolicy(
        narration_timing=NarrationTimingPolicy.FIT_TO_VIDEO,
    )


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


def test_request_derives_legacy_timeline_when_one_is_not_supplied() -> None:
    """Legacy render requests should still gain an explicit production timeline deterministically."""

    request = ShortRenderRequest(scenes=[build_scene(duration_seconds=3.0), build_scene(scene_number=2, duration_seconds=4.0)])

    assert request.production_timeline is not None
    assert [scene.scene_number for scene in request.production_timeline.scenes] == [1, 2]
    assert request.production_timeline.total_duration_seconds == 7.0


def test_explicit_production_timeline_must_match_scene_order() -> None:
    """Timeline scenes should align exactly with render-scene numbering."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(
            scenes=[build_scene(scene_number=1), build_scene(scene_number=2)],
            production_timeline=ProductionTimeline(
                scenes=[
                    ProductionTimelineScene(
                        scene_number=1,
                        start_seconds=0.0,
                        end_seconds=3.0,
                        duration_seconds=3.0,
                        source_asset_ref=build_image_asset("mock://generated/image/1.png"),
                    ),
                    ProductionTimelineScene(
                        scene_number=3,
                        start_seconds=3.0,
                        end_seconds=6.0,
                        duration_seconds=3.0,
                        source_asset_ref=build_image_asset("mock://generated/image/3.png"),
                    ),
                ],
                target_duration_seconds=6.0,
            ),
        )


def test_narration_duration_may_be_absent_without_fabrication() -> None:
    """Missing narration duration should remain unset and still validate."""

    request = ShortRenderRequest(
        scenes=[build_scene()],
        production_timeline=build_timeline(durations=(3.0,)),
        narration=build_audio(duration=None),
    )

    assert request.narration is not None
    assert request.narration.estimated_duration_seconds is None


def test_narration_duration_cannot_exceed_scene_duration_by_large_margin() -> None:
    """Known narration duration should remain within the documented tolerance."""

    with pytest.raises(ValidationError):
        ShortRenderRequest(
            scenes=[build_scene(duration_seconds=3.0)],
            production_timeline=build_timeline(durations=(3.0,)),
            narration=build_audio(duration=4.5),
        )


def test_timeline_scene_rejects_provider_specific_fields_in_payload() -> None:
    """The provider-neutral timeline model should not accept FFmpeg-specific fields."""

    with pytest.raises(ValidationError):
        ProductionTimelineScene.model_validate(
            {
                "scene_number": 1,
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "duration_seconds": 3.0,
                "source_asset_ref": build_image_asset().model_dump(mode="json"),
                "ffmpeg_filter": "scale=1080:1920",
            }
        )


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
