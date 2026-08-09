"""Application-layer final Short assembly without direct provider access."""

from __future__ import annotations

from pydantic import Field, field_validator

from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.storyboard import StoryboardSceneBreakdownOutput
from creatoros.providers import CaptionOverlay, RenderedVideo, RenderScene, ShortRenderRequest
from creatoros.services.media_generation import GeneratedMediaPackage
from creatoros.services.media_render import MediaRenderService, create_media_render_service


def _copy_model[TModel: CreatorOSModel](value: TModel) -> TModel:
    """Return one deep-copied CreatorOS model for isolated service inputs."""

    return value.model_copy(deep=True)


class ShortAssemblyRequest(CreatorOSModel):
    """Minimum typed inputs required to assemble a renderable Short request."""

    storyboard: StoryboardSceneBreakdownOutput
    generated_media: GeneratedMediaPackage

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

        render_scenes = [
            RenderScene(
                scene_number=scene.scene_number,
                duration_seconds=scene.duration_seconds,
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
                    else CaptionOverlay(text=scene.on_screen_text)
                ),
            )
            for index, scene in enumerate(request.storyboard.scenes)
        ]

        return ShortRenderRequest(
            scenes=render_scenes,
            narration=(
                None
                if generated_media.narration is None
                else generated_media.narration.model_copy(deep=True)
            ),
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
