"""Provider-neutral render and composition contracts for CreatorOS Shorts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import Field, computed_field, field_validator, model_validator

from creatoros.domain import AssetType, CreatorOSModel, GeneratedAsset
from creatoros.providers.media import GeneratedAudio


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_string(value: str | None, *, field_name: str) -> str | None:
    """Trim optional text values and normalize blanks to ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _validate_positive_finite_float(value: float, *, field_name: str) -> float:
    """Require positive finite float values."""

    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return value


class RenderTransition(StrEnum):
    """Tiny provider-neutral transition set for the initial render contract."""

    CUT = "cut"
    FADE = "fade"


class CaptionPosition(StrEnum):
    """Provider-neutral caption anchor positions for simple Short overlays."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class CaptionOverlay(CreatorOSModel):
    """Provider-neutral caption overlay instructions for one render scene."""

    text: str
    position: CaptionPosition = CaptionPosition.BOTTOM
    max_lines: int = Field(default=2, gt=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Trim and reject blank caption text."""

        return _validate_non_blank(value, field_name="text")


class RenderScene(CreatorOSModel):
    """One planned scene in a future composed Short render."""

    scene_number: int
    duration_seconds: float
    visual_asset_ref: GeneratedAsset | None = None
    video_asset_ref: GeneratedAsset | None = None
    caption: CaptionOverlay | None = None
    motion_instruction: str | None = None
    transition: RenderTransition = RenderTransition.CUT

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Require scene numbers to start at one."""

        if value <= 0:
            raise ValueError("scene_number must be greater than zero")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive finite scene durations."""

        return _validate_positive_finite_float(value, field_name="duration_seconds")

    @field_validator("motion_instruction")
    @classmethod
    def normalize_optional_text(cls, value: str | None, info) -> str | None:
        """Normalize optional planning text."""

        return _normalize_optional_string(value, field_name=info.field_name)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_caption_fields(cls, value: object) -> object:
        """Support legacy caption field inputs while normalizing to ``caption``."""

        if not isinstance(value, dict):
            return value

        if value.get("caption") is not None:
            return value

        caption_text = value.pop("caption_text", None)
        caption_position = value.pop("caption_position", None)
        caption_max_lines = value.pop("caption_max_lines", None)
        if caption_text is None:
            return value

        normalized_caption_text = caption_text.strip()
        if not normalized_caption_text:
            return value

        caption_payload: dict[str, object] = {"text": normalized_caption_text}
        if caption_position is not None:
            caption_payload["position"] = caption_position
        if caption_max_lines is not None:
            caption_payload["max_lines"] = caption_max_lines
        value["caption"] = caption_payload
        return value

    @model_validator(mode="after")
    def validate_asset_references(self) -> RenderScene:
        """Require at least one visual or video asset reference per scene."""

        if self.visual_asset_ref is None and self.video_asset_ref is None:
            raise ValueError("at least one asset reference is required")
        if self.visual_asset_ref is not None and self.visual_asset_ref.asset_type is not AssetType.IMAGE:
            raise ValueError("visual_asset_ref.asset_type must be image")
        if self.video_asset_ref is not None and self.video_asset_ref.asset_type is not AssetType.VIDEO:
            raise ValueError("video_asset_ref.asset_type must be video")
        return self

    @property
    def caption_text(self) -> str | None:
        """Return the legacy caption text convenience view."""

        if self.caption is None:
            return None
        return self.caption.text


class ShortRenderRequest(CreatorOSModel):
    """Provider-neutral request for deterministic future Short composition."""

    scenes: list[RenderScene]
    narration: GeneratedAudio | None = None
    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)
    fps: float = 30.0
    output_format: str = "mp4"
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("scenes")
    @classmethod
    def validate_scenes_present(cls, value: list[RenderScene]) -> list[RenderScene]:
        """Require at least one scene."""

        if not value:
            raise ValueError("scenes must contain at least one scene")
        return value

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, value: float) -> float:
        """Require positive finite frame-rate values."""

        return _validate_positive_finite_float(value, field_name="fps")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        """Normalize the symbolic output format identifier."""

        return _validate_non_blank(value.lower(), field_name="output_format")

    @model_validator(mode="after")
    def validate_timeline(self) -> ShortRenderRequest:
        """Require sequential scenes and bounded narration duration when present."""

        scene_numbers = [scene.scene_number for scene in self.scenes]
        expected_numbers = list(range(1, len(self.scenes) + 1))
        if scene_numbers != expected_numbers:
            raise ValueError("scene numbers must be sequential starting at 1")

        narration_duration = (
            None if self.narration is None else self.narration.estimated_duration_seconds
        )
        if narration_duration is not None and narration_duration > self.total_duration_seconds + 1.0:
            raise ValueError(
                "narration estimated_duration_seconds must not exceed total_duration_seconds by more than 1.0",
            )
        return self

    if TYPE_CHECKING:

        @property
        def total_duration_seconds(self) -> float:
            """Return the deterministic sum of scene durations."""

    else:

        @computed_field(return_type=float)
        @property
        def total_duration_seconds(self) -> float:
            """Return the deterministic sum of scene durations."""

            return round(sum(scene.duration_seconds for scene in self.scenes), 6)


class RenderedVideo(CreatorOSModel):
    """Provider-neutral result for one composed Short render."""

    artifact: GeneratedAsset
    provider_name: str
    mime_type: str
    duration_seconds: float
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("provider_name", "mime_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required result identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("duration_seconds", "fps")
    @classmethod
    def validate_positive_floats(cls, value: float, info) -> float:
        """Require positive finite duration and frame-rate values."""

        return _validate_positive_finite_float(value, field_name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        """Normalize optional request identifiers."""

        return _normalize_optional_string(value, field_name="request_id")

    @model_validator(mode="after")
    def validate_artifact_type(self) -> RenderedVideo:
        """Require a video artifact reference."""

        if self.artifact.asset_type is not AssetType.VIDEO:
            raise ValueError("artifact.asset_type must be video")
        return self


__all__ = [
    "CaptionOverlay",
    "CaptionPosition",
    "RenderScene",
    "RenderTransition",
    "RenderedVideo",
    "ShortRenderRequest",
]
