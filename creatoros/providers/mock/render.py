"""Deterministic mock render provider for CreatorOS Short composition."""

from __future__ import annotations

import hashlib
import json

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase
from creatoros.providers.render import RenderedVideo, ShortRenderRequest


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


def _build_digest(request: ShortRenderRequest) -> str:
    """Create one stable mock artifact digest from render inputs."""

    production_timeline = None
    if request.production_timeline is not None:
        production_timeline = {
            "target_duration_seconds": request.production_timeline.target_duration_seconds,
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "start_seconds": scene.start_seconds,
                    "end_seconds": scene.end_seconds,
                    "duration_seconds": scene.duration_seconds,
                    "source_asset_type": scene.source_asset_ref.asset_type.value,
                    "source_asset_uri": scene.source_asset_ref.uri,
                    "trim_start_seconds": scene.trim_start_seconds,
                    "trim_end_seconds": scene.trim_end_seconds,
                    "caption_text": scene.caption_text,
                    "caption_position": scene.caption_position.value,
                    "caption_max_lines": scene.caption_max_lines,
                    "caption_style": scene.caption_style.model_dump(mode="json"),
                    "narration_start_seconds": scene.narration_start_seconds,
                    "narration_end_seconds": scene.narration_end_seconds,
                    "visual_treatment": scene.visual_treatment.model_dump(mode="json"),
                }
                for scene in request.production_timeline.scenes
            ],
        }

    payload = {
        "scenes": [
            {
                "scene_number": scene.scene_number,
                "duration_seconds": scene.duration_seconds,
                "visual_asset_uri": None if scene.visual_asset_ref is None else scene.visual_asset_ref.uri,
                "video_asset_uri": None if scene.video_asset_ref is None else scene.video_asset_ref.uri,
                "caption_text": scene.caption_text,
                "caption_style": None if scene.caption is None else scene.caption.style.model_dump(mode="json"),
                "motion_instruction": scene.motion_instruction,
                "transition": scene.transition,
            }
            for scene in request.scenes
        ],
        "production_timeline": production_timeline,
        "narration_uri": None if request.narration is None else request.narration.artifact.uri,
        "narration_duration": (
            None if request.narration is None else request.narration.estimated_duration_seconds
        ),
        "width": request.width,
        "height": request.height,
        "fps": request.fps,
        "output_format": request.output_format,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class MockRenderProvider(MockProviderBase):
    """Deterministic render provider that composes planning data without files."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="render",
            capabilities={ProviderCapability.RENDERING},
            is_healthy=is_healthy,
        )

    async def render(
        self,
        request: ShortRenderRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[RenderedVideo]:
        """Return one deterministic rendered-video contract without local rendering."""

        del context
        digest = _build_digest(request)
        timeline = request.production_timeline
        artifact = GeneratedAsset(
            asset_type=AssetType.VIDEO,
            uri=f"mock://rendered/video/{digest}.mp4",
            metadata={"mock_artifact_id": digest},
        )
        result = RenderedVideo(
            artifact=artifact,
            provider_name=self.info.name,
            mime_type="video/mp4",
            duration_seconds=request.total_duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            request_id=f"mock_render_request_{digest}",
            metadata={
                "mock": True,
                "scene_count": len(request.scenes),
                "output_format": request.output_format,
                "has_narration": request.narration is not None,
                "timeline_scene_count": len(request.scenes) if timeline is None else len(timeline.scenes),
                "caption_styles": (
                    []
                    if timeline is None
                    else [scene.caption_style.model_dump(mode="json") for scene in timeline.scenes]
                ),
                "visual_treatments": (
                    []
                    if timeline is None
                    else [scene.visual_treatment.model_dump(mode="json") for scene in timeline.scenes]
                ),
            },
        )
        return ProviderResult[RenderedVideo](
            data=result,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=result.request_id,
        )


__all__ = ["MockRenderProvider"]
