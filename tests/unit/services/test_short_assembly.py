"""Unit tests for the CreatorOS final Short assembly service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderNotFoundError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.parsing.storyboard import StoryboardSceneBreakdownOutput, StoryboardScenePlan
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ProviderCapability,
    ProviderInfo,
    create_provider_registry,
)
from creatoros.providers.mock import MockRenderProvider
from creatoros.providers.render import RenderedVideo, RenderTransition, ShortRenderRequest
from creatoros.services import (
    GeneratedMediaPackage,
    MediaRenderService,
    ShortAssemblyRequest,
    ShortAssemblyResult,
    ShortAssemblyService,
    create_short_assembly_service,
)

_USE_STORYBOARD_DURATION = object()


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


def build_storyboard(scene_count: int = 2) -> StoryboardSceneBreakdownOutput:
    """Create a valid typed storyboard for assembly tests."""

    scenes = tuple(
        StoryboardScenePlan(
            scene_number=index,
            purpose=f"Purpose {index}",
            script_beat=f"Beat {index}",
            visual=f"Visual {index}",
            on_screen_text=f"Caption {index}",
            duration_seconds=float(index + 2),
        )
        for index in range(1, scene_count + 1)
    )
    return StoryboardSceneBreakdownOutput(
        storyboard_title="Roblox: Funny Myths",
        scenes=scenes,
        final_scene_count=scene_count,
        total_estimated_duration_seconds=sum(scene.duration_seconds for scene in scenes),
    )


def build_generated_image(index: int) -> GeneratedImage:
    """Create one generated image result."""

    return GeneratedImage(
        artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri=f"mock://generated/image/{index}.png"),
        provider_name="mock",
        model="mock-image-model",
        mime_type="image/png",
        width=1024,
        height=1024,
        metadata={"index": index},
    )


def build_generated_video(index: int, *, duration_seconds: float) -> GeneratedVideo:
    """Create one generated video result."""

    return GeneratedVideo(
        artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri=f"mock://generated/video/{index}.mp4"),
        provider_name="mock",
        model="mock-video-model",
        mime_type="video/mp4",
        duration_seconds=duration_seconds,
        width=1080,
        height=1920,
        fps=30.0,
        metadata={"index": index},
    )


def build_generated_audio(*, estimated_duration_seconds: float | None = 7.0) -> GeneratedAudio:
    """Create one generated narration result."""

    return GeneratedAudio(
        artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
        provider_name="mock",
        model="mock-tts-model",
        mime_type="audio/wav",
        estimated_duration_seconds=estimated_duration_seconds,
    )


def build_generated_media_package(
    *,
    scene_count: int = 2,
    include_thumbnail: bool = True,
    include_narration: bool = True,
    include_images: bool = True,
    include_videos: bool = False,
    narration_duration: float | None | object = _USE_STORYBOARD_DURATION,
) -> GeneratedMediaPackage:
    """Create one generated-media package for assembly tests."""

    storyboard = build_storyboard(scene_count)
    resolved_narration_duration = (
        storyboard.total_estimated_duration_seconds
        if narration_duration is _USE_STORYBOARD_DURATION and include_narration
        else narration_duration
    )
    return GeneratedMediaPackage(
        thumbnail=build_generated_image(999) if include_thumbnail else None,
        narration=(
            build_generated_audio(estimated_duration_seconds=resolved_narration_duration)
            if include_narration
            else None
        ),
        scene_images=(
            tuple(build_generated_image(index) for index in range(1, scene_count + 1))
            if include_images
            else ()
        ),
        scene_videos=(
            tuple(
                build_generated_video(index, duration_seconds=storyboard.scenes[index - 1].duration_seconds)
                for index in range(1, scene_count + 1)
            )
            if include_videos
            else ()
        ),
    )


def build_request(
    *,
    scene_count: int = 2,
    include_thumbnail: bool = True,
    include_narration: bool = True,
    include_images: bool = True,
    include_videos: bool = False,
    narration_duration: float | None | object = _USE_STORYBOARD_DURATION,
) -> ShortAssemblyRequest:
    """Create a valid assembly request."""

    return ShortAssemblyRequest(
        storyboard=build_storyboard(scene_count),
        generated_media=build_generated_media_package(
            scene_count=scene_count,
            include_thumbnail=include_thumbnail,
            include_narration=include_narration,
            include_images=include_images,
            include_videos=include_videos,
            narration_duration=narration_duration,
        ),
    )


class RecordingRenderProvider(MockRenderProvider):
    """Render provider that records forwarded render requests."""

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


def build_render_service(*, default_render_provider: str = "mock") -> tuple[MediaRenderService, RecordingRenderProvider]:
    """Create one recording render service for assembly tests."""

    registry = create_provider_registry()
    provider = RecordingRenderProvider(name=default_render_provider)
    registry.register(provider)
    return MediaRenderService(registry, build_settings(default_render_provider=default_render_provider)), provider


def test_service_accepts_media_render_service_dependency() -> None:
    """The assembly service should accept the render-service dependency."""

    render_service, _provider = build_render_service()

    service = ShortAssemblyService(render_service)

    assert isinstance(service, ShortAssemblyService)


def test_invalid_dependency_is_rejected_safely() -> None:
    """Invalid assembly-service dependencies should fail with typed errors."""

    with pytest.raises(CreatorOSValidationError):
        ShortAssemblyService(object())  # type: ignore[arg-type]


def test_request_deep_copies_input_models() -> None:
    """Request construction should isolate nested mutable model state."""

    storyboard = build_storyboard()
    generated_media = build_generated_media_package()
    request = ShortAssemblyRequest(storyboard=storyboard, generated_media=generated_media)

    storyboard.scenes[0].on_screen_text = "Mutated caption"
    generated_media.scene_images[0].metadata["index"] = 12345

    assert request.storyboard.scenes[0].on_screen_text == "Caption 1"
    assert request.generated_media.scene_images[0].metadata["index"] == 1


def test_single_storyboard_scene_maps_to_one_scene_image() -> None:
    """A one-scene storyboard should map to one render scene deterministically."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)

    render_request = service.build_render_request(build_request(scene_count=1, include_videos=False))

    assert len(render_request.scenes) == 1
    assert render_request.scenes[0].scene_number == 1
    assert render_request.scenes[0].duration_seconds == 3.0
    assert render_request.scenes[0].visual_asset_ref is not None
    assert render_request.scenes[0].visual_asset_ref.uri == "mock://generated/image/1.png"
    assert render_request.scenes[0].video_asset_ref is None
    assert render_request.scenes[0].caption_text == "Caption 1"
    assert render_request.scenes[0].motion_instruction is None
    assert render_request.scenes[0].transition is RenderTransition.CUT


def test_multiple_scenes_map_in_deterministic_order_without_drops_or_duplicates() -> None:
    """Scene assets should align by index and preserve both image and video references."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)

    render_request = service.build_render_request(build_request(include_videos=True))

    assert [scene.scene_number for scene in render_request.scenes] == [1, 2]
    assert [scene.visual_asset_ref.uri for scene in render_request.scenes if scene.visual_asset_ref is not None] == [
        "mock://generated/image/1.png",
        "mock://generated/image/2.png",
    ]
    assert [scene.video_asset_ref.uri for scene in render_request.scenes if scene.video_asset_ref is not None] == [
        "mock://generated/video/1.mp4",
        "mock://generated/video/2.mp4",
    ]
    assert len({scene.visual_asset_ref.uri for scene in render_request.scenes if scene.visual_asset_ref is not None}) == 2
    assert len({scene.video_asset_ref.uri for scene in render_request.scenes if scene.video_asset_ref is not None}) == 2


def test_incompatible_image_count_is_rejected_before_rendering() -> None:
    """Scene-image counts must either match the storyboard or stay empty."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)
    request = build_request()
    request.generated_media.scene_images = request.generated_media.scene_images[:1]

    with pytest.raises(CreatorOSValidationError) as exc_info:
        service.build_render_request(request)

    assert exc_info.value.code == "short_assembly_asset_count_mismatch"
    assert exc_info.value.details["asset_name"] == "scene_images"


def test_incompatible_video_count_is_rejected_before_rendering() -> None:
    """Scene-video counts must either match the storyboard or stay empty."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)
    request = build_request(include_videos=True)
    request.generated_media.scene_videos = request.generated_media.scene_videos[:1]

    with pytest.raises(CreatorOSValidationError) as exc_info:
        service.build_render_request(request)

    assert exc_info.value.code == "short_assembly_asset_count_mismatch"
    assert exc_info.value.details["asset_name"] == "scene_videos"


def test_missing_scene_assets_are_rejected_before_rendering() -> None:
    """Assembly should fail fast when no per-scene assets exist at all."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        service.build_render_request(build_request(include_images=False, include_videos=False))

    assert exc_info.value.code == "short_assembly_missing_scene_assets"


def test_thumbnail_is_not_inserted_into_timeline_and_remains_available() -> None:
    """The package thumbnail should remain separate from the render timeline."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)
    request = build_request(include_thumbnail=True, scene_count=2)

    render_request = service.build_render_request(request)

    assert len(render_request.scenes) == 2
    assert all(scene.visual_asset_ref.uri != "mock://generated/image/999.png" for scene in render_request.scenes)
    assert request.generated_media.thumbnail is not None
    assert request.generated_media.thumbnail.artifact.uri == "mock://generated/image/999.png"


def test_narration_maps_without_inventing_duration() -> None:
    """Narration should pass through unchanged, including missing duration estimates."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)

    with_duration = service.build_render_request(build_request(narration_duration=7.0))
    without_duration = service.build_render_request(build_request(narration_duration=None))

    assert with_duration.narration is not None
    assert with_duration.narration.artifact.uri == "mock://generated/audio/narration.wav"
    assert with_duration.narration.estimated_duration_seconds == 7.0
    assert without_duration.narration is not None
    assert without_duration.narration.estimated_duration_seconds is None


def test_build_render_request_is_deterministic_and_does_not_mutate_source_request() -> None:
    """Building twice from the same request should produce equal render requests safely."""

    render_service, _provider = build_render_service()
    service = ShortAssemblyService(render_service)
    request = build_request(include_videos=True)
    original_dump = request.model_dump(mode="json")

    first = service.build_render_request(request)
    second = service.build_render_request(request)

    assert first == second
    assert isinstance(first, ShortRenderRequest)
    assert first.total_duration_seconds == 7.0
    assert request.model_dump(mode="json") == original_dump


def test_assemble_invokes_media_render_service_once_and_forwards_override() -> None:
    """Assemble should call the render service once and forward provider overrides."""

    registry = create_provider_registry()
    default_provider = RecordingRenderProvider(name="mock")
    alternate_provider = RecordingRenderProvider(name="alternate")
    registry.register(default_provider)
    registry.register(alternate_provider)
    render_service = MediaRenderService(registry, build_settings(default_render_provider="mock"))
    service = ShortAssemblyService(render_service)

    result = asyncio.run(service.assemble(build_request(include_videos=True), render_provider_name="alternate"))

    assert isinstance(result, ShortAssemblyResult)
    assert isinstance(result.rendered_video, RenderedVideo)
    assert alternate_provider.calls == 1
    assert default_provider.calls == 0
    assert alternate_provider.last_request == result.render_request
    assert result.scene_count == 2
    assert result.total_duration_seconds == 7.0


def test_render_failure_propagates_safely() -> None:
    """Render-provider failures should propagate without fake success."""

    service = create_short_assembly_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(service.assemble(build_request(), render_provider_name="missing"))


def test_mock_end_to_end_assembly_returns_typed_result_without_real_media_output() -> None:
    """Typed assembly should complete end to end through the deterministic mock renderer."""

    service = create_short_assembly_service(settings=build_settings())

    result = asyncio.run(service.assemble(build_request(include_videos=True)))

    assert isinstance(result.render_request, ShortRenderRequest)
    assert isinstance(result.rendered_video, RenderedVideo)
    assert result.rendered_video.provider_name == "mock"
    assert result.rendered_video.artifact.uri.startswith("mock://rendered/video/")
    assert result.generated_media.thumbnail is not None


def test_service_source_respects_boundaries_and_avoids_heavy_rendering_side_effects() -> None:
    """The assembly service should remain a narrow mapping and render-coordination layer."""

    source = Path("creatoros/services/short_assembly.py").read_text(encoding="utf-8")

    assert "ProviderRegistry" not in source
    assert "MediaGenerationService" not in source
    assert "LLMExecutionService" not in source
    assert "GamingMediaAgent" not in source
    assert "GamingStoryboardAgent" not in source
    assert "GamingScriptAgent" not in source
    assert "OpenAI" not in source
    assert "ffmpeg" not in source.lower()
    assert "moviepy" not in source.lower()
    assert "open(" not in source
    assert "write_text" not in source
