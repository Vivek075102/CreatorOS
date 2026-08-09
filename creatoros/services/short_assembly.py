"""Application-layer final Short assembly without direct provider access."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import Field, field_validator

from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.storyboard import StoryboardSceneBreakdownOutput
from creatoros.providers import (
    CaptionEmphasis,
    CaptionFontSizeProfile,
    CaptionOverlay,
    CaptionStylePolicy,
    ProductionTimeline,
    ProductionTimelineScene,
    RenderedVideo,
    RenderScene,
    ShortRenderRequest,
    build_default_visual_treatment,
)
from creatoros.services.media_generation import GeneratedMediaPackage
from creatoros.services.media_render import MediaRenderService, create_media_render_service

_TIMELINE_SCALE = Decimal(1000000)


def _default_caption_style_policy() -> CaptionStylePolicy:
    """Return one deterministic caption-style default for assembled Shorts."""

    return CaptionStylePolicy(
        emphasis=CaptionEmphasis.KEYWORD,
        font_size_profile=CaptionFontSizeProfile.LARGE,
        max_chars_per_line=28,
    )


def _quantize_seconds(value: Decimal) -> float:
    """Convert one Decimal microsecond duration into a stable float seconds value."""

    return float((value / _TIMELINE_SCALE).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _calculate_paced_scene_durations(
    *,
    source_durations: tuple[float, ...],
    target_duration_seconds: float,
) -> tuple[float, ...]:
    """Build one deterministic paced scene-duration tuple that sums to the target exactly."""

    if not source_durations:
        raise CreatorOSValidationError(
            "storyboard must contain at least one scene",
            code="short_assembly_timeline_invalid",
        )

    target_units = int(
        (Decimal(str(target_duration_seconds)) * _TIMELINE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    if target_units < len(source_durations):
        raise CreatorOSValidationError(
            "target duration is too small for the scene count",
            code="short_assembly_timeline_invalid",
            details={"scene_count": len(source_durations), "target_duration_seconds": target_duration_seconds},
        )

    source_unit_weights = tuple(
        int((Decimal(str(duration)) * _TIMELINE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        for duration in source_durations
    )
    total_source_units = sum(source_unit_weights)
    if total_source_units <= 0:
        raise CreatorOSValidationError(
            "storyboard scene durations must be greater than zero",
            code="short_assembly_timeline_invalid",
        )

    remaining_distributable_units = target_units - len(source_durations)
    paced_units: list[int] = []
    allocated_units = 0
    for source_units in source_unit_weights[:-1]:
        extra_units = (remaining_distributable_units * source_units) // total_source_units
        scene_units = 1 + extra_units
        paced_units.append(scene_units)
        allocated_units += scene_units

    last_scene_units = target_units - allocated_units
    if last_scene_units <= 0:
        raise CreatorOSValidationError(
            "timeline pacing produced a non-positive final scene duration",
            code="short_assembly_timeline_invalid",
        )
    paced_units.append(last_scene_units)
    return tuple(_quantize_seconds(Decimal(scene_units)) for scene_units in paced_units)


def _build_production_timeline(
    *,
    storyboard: StoryboardSceneBreakdownOutput,
    generated_media: GeneratedMediaPackage,
) -> ProductionTimeline:
    """Build one deterministic provider-neutral production timeline from storyboard order and target duration."""

    target_duration_seconds = storyboard.total_estimated_duration_seconds
    paced_durations = _calculate_paced_scene_durations(
        source_durations=tuple(scene.duration_seconds for scene in storyboard.scenes),
        target_duration_seconds=target_duration_seconds,
    )
    narration_duration = (
        None if generated_media.narration is None else generated_media.narration.estimated_duration_seconds
    )
    if narration_duration is not None and narration_duration > target_duration_seconds + 1e-6:
        raise CreatorOSValidationError(
            "generated narration duration exceeds the target short duration",
            code="short_assembly_narration_too_long",
            details={
                "narration_duration_seconds": narration_duration,
                "target_duration_seconds": target_duration_seconds,
            },
        )

    timeline_scenes: list[ProductionTimelineScene] = []
    current_start = 0.0
    for index, (storyboard_scene, paced_duration) in enumerate(
        zip(storyboard.scenes, paced_durations, strict=True),
    ):
        current_end = round(current_start + paced_duration, 6)
        source_asset_ref = (
            generated_media.scene_videos[index].artifact.model_copy(deep=True)
            if generated_media.scene_videos
            else generated_media.scene_images[index].artifact.model_copy(deep=True)
        )
        narration_start_seconds = None
        narration_end_seconds = None
        if narration_duration is not None:
            overlap_start = current_start
            overlap_end = min(current_end, narration_duration)
            if overlap_end > overlap_start:
                narration_start_seconds = overlap_start
                narration_end_seconds = overlap_end
        next_source_asset_type = None
        if index + 1 < len(storyboard.scenes):
            if generated_media.scene_videos:
                next_source_asset_type = generated_media.scene_videos[index + 1].artifact.asset_type
            else:
                next_source_asset_type = generated_media.scene_images[index + 1].artifact.asset_type
        timeline_scenes.append(
            ProductionTimelineScene(
                scene_number=storyboard_scene.scene_number,
                start_seconds=current_start,
                end_seconds=current_end,
                duration_seconds=round(paced_duration, 6),
                source_asset_ref=source_asset_ref,
                caption_text=storyboard_scene.on_screen_text,
                caption_style=_default_caption_style_policy(),
                narration_start_seconds=narration_start_seconds,
                narration_end_seconds=narration_end_seconds,
                visual_treatment=build_default_visual_treatment(
                    scene_number=storyboard_scene.scene_number,
                    source_asset_type=source_asset_ref.asset_type,
                    next_source_asset_type=next_source_asset_type,
                ),
            )
        )
        current_start = current_end
    return ProductionTimeline(
        scenes=timeline_scenes,
        target_duration_seconds=target_duration_seconds,
    )


def _copy_model[TModel: CreatorOSModel](value: TModel) -> TModel:
    """Return one deep-copied CreatorOS model for isolated service inputs."""

    return value.model_copy(deep=True)


class ShortAssemblyRequest(CreatorOSModel):
    """Minimum typed inputs required to assemble a renderable Short request."""

    storyboard: StoryboardSceneBreakdownOutput
    generated_media: GeneratedMediaPackage
    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)
    fps: float = Field(default=30.0, gt=0)
    output_format: str = "mp4"

    @field_validator("storyboard", "generated_media", mode="before")
    @classmethod
    def copy_models(cls, value: object, info) -> CreatorOSModel:
        """Protect the request from external mutation by deep-copying models."""

        if not isinstance(value, CreatorOSModel):
            raise TypeError(f"{info.field_name} must be a CreatorOS model")
        return _copy_model(value)


class ShortAssemblyResult(CreatorOSModel):
    """Typed assembly result for later persistence or publishing integration."""

    render_request: ShortRenderRequest
    rendered_video: RenderedVideo
    generated_media: GeneratedMediaPackage
    scene_count: int = Field(gt=0)
    total_duration_seconds: float = Field(gt=0)

    @field_validator("render_request", "rendered_video", "generated_media", mode="before")
    @classmethod
    def copy_models(cls, value: object, info) -> CreatorOSModel:
        """Protect the result from external mutation by deep-copying models."""

        if not isinstance(value, CreatorOSModel):
            raise TypeError(f"{info.field_name} must be a CreatorOS model")
        return _copy_model(value)


class ShortAssemblyService:
    """Build typed render requests and delegate final composition to the render service."""

    def __init__(self, media_render_service: MediaRenderService) -> None:
        if not isinstance(media_render_service, MediaRenderService):
            raise CreatorOSValidationError(
                "media_render_service must be a MediaRenderService",
                code="service_invalid_dependency",
                details={"dependency": "media_render_service"},
            )
        self.media_render_service = media_render_service

    def build_render_request(self, request: ShortAssemblyRequest) -> ShortRenderRequest:
        """Build one deterministic Short render request without provider calls."""

        scene_count = len(request.storyboard.scenes)
        generated_media = request.generated_media

        self._validate_alignment(scene_count, len(generated_media.scene_images), asset_name="scene_images")
        self._validate_alignment(scene_count, len(generated_media.scene_videos), asset_name="scene_videos")

        if not generated_media.scene_images and not generated_media.scene_videos:
            raise CreatorOSValidationError(
                "generated_media must include scene images or scene videos",
                code="short_assembly_missing_scene_assets",
                details={"scene_count": scene_count},
            )

        production_timeline = _build_production_timeline(
            storyboard=request.storyboard,
            generated_media=generated_media,
        )
        render_scenes = [
            RenderScene(
                scene_number=scene.scene_number,
                duration_seconds=production_timeline.scenes[index].duration_seconds,
                visual_asset_ref=(
                    None
                    if not generated_media.scene_images
                    else generated_media.scene_images[index].artifact.model_copy(deep=True)
                ),
                video_asset_ref=(
                    None
                    if not generated_media.scene_videos
                    else generated_media.scene_videos[index].artifact.model_copy(deep=True)
                ),
                caption=(
                    None
                    if scene.on_screen_text is None
                    else CaptionOverlay(text=scene.on_screen_text, style=_default_caption_style_policy())
                ),
            )
            for index, scene in enumerate(request.storyboard.scenes)
        ]

        return ShortRenderRequest(
            scenes=render_scenes,
            production_timeline=production_timeline,
            narration=(
                None
                if generated_media.narration is None
                else generated_media.narration.model_copy(deep=True)
            ),
            width=request.width,
            height=request.height,
            fps=request.fps,
            output_format=request.output_format,
        )

    async def assemble(
        self,
        request: ShortAssemblyRequest,
        *,
        render_provider_name: str | None = None,
    ) -> ShortAssemblyResult:
        """Assemble typed media inputs into one rendered-video result."""

        render_request = self.build_render_request(request)
        rendered_video_result = await self.media_render_service.render(
            render_request,
            provider_name=render_provider_name,
        )
        return ShortAssemblyResult(
            render_request=render_request,
            rendered_video=rendered_video_result.data,
            generated_media=request.generated_media,
            scene_count=len(render_request.scenes),
            total_duration_seconds=render_request.total_duration_seconds,
        )

    @staticmethod
    def _validate_alignment(scene_count: int, asset_count: int, *, asset_name: str) -> None:
        """Require exact scene-to-asset alignment when scene assets are supplied."""

        if asset_count not in {0, scene_count}:
            raise CreatorOSValidationError(
                f"{asset_name} must be empty or match storyboard scene count",
                code="short_assembly_asset_count_mismatch",
                details={
                    "asset_name": asset_name,
                    "scene_count": scene_count,
                    "asset_count": asset_count,
                },
            )


def create_short_assembly_service(
    *,
    media_render_service: MediaRenderService | None = None,
    settings: Settings | None = None,
) -> ShortAssemblyService:
    """Create a safe default final-assembly service using the render-service factory."""

    resolved_media_render_service = (
        create_media_render_service(settings=settings)
        if media_render_service is None
        else media_render_service
    )
    return ShortAssemblyService(resolved_media_render_service)


__all__ = [
    "ShortAssemblyRequest",
    "ShortAssemblyResult",
    "ShortAssemblyService",
    "create_short_assembly_service",
]
