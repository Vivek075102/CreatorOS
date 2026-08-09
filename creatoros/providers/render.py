"""Provider-neutral render and composition contracts for CreatorOS Shorts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import Field, computed_field, field_validator, model_validator

from creatoros.core import CreatorOSValidationError
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
    CROSSFADE = "crossfade"


class VisualMotion(StrEnum):
    """Provider-neutral visual motion treatments for final Short scenes."""

    NONE = "none"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"


class VisualMotionIntensity(StrEnum):
    """Small provider-neutral motion-intensity set for deterministic editorial movement."""

    SUBTLE = "subtle"
    NORMAL = "normal"


class NarrationTimingPolicy(StrEnum):
    """Provider-neutral narration timing policy for final Short composition."""

    FIT_TO_VIDEO = "fit_to_video"


class CaptionPosition(StrEnum):
    """Provider-neutral caption anchor positions for simple Short overlays."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class CaptionEmphasis(StrEnum):
    """Deterministic provider-neutral caption emphasis modes."""

    NONE = "none"
    KEYWORD = "keyword"
    ACTIVE_PHRASE = "active_phrase"


class CaptionFontSizeProfile(StrEnum):
    """Provider-neutral caption font-size profiles."""

    STANDARD = "standard"
    LARGE = "large"


class CaptionTextAlignment(StrEnum):
    """Provider-neutral horizontal text alignment for captions."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class CaptionSafeMarginProfile(StrEnum):
    """Provider-neutral safe-margin profiles for caption placement."""

    COMFORTABLE = "comfortable"
    TIGHT = "tight"


class CaptionStylePolicy(CreatorOSModel):
    """Provider-neutral styling policy for caption emphasis, wrapping, and safe placement."""

    emphasis: CaptionEmphasis = CaptionEmphasis.NONE
    font_size_profile: CaptionFontSizeProfile = CaptionFontSizeProfile.STANDARD
    text_alignment: CaptionTextAlignment = CaptionTextAlignment.CENTER
    safe_margin_profile: CaptionSafeMarginProfile = CaptionSafeMarginProfile.COMFORTABLE
    max_chars_per_line: int = Field(default=32, gt=0)


class CaptionOverlay(CreatorOSModel):
    """Provider-neutral caption overlay instructions for one render scene."""

    text: str
    position: CaptionPosition = CaptionPosition.BOTTOM
    max_lines: int = Field(default=2, gt=0)
    style: CaptionStylePolicy = Field(default_factory=CaptionStylePolicy)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Trim and reject blank caption text."""

        return _validate_non_blank(value, field_name="text")


class SceneVisualTreatment(CreatorOSModel):
    """Provider-neutral visual treatment instructions for one production-timeline scene."""

    motion: VisualMotion = VisualMotion.NONE
    intensity: VisualMotionIntensity = VisualMotionIntensity.SUBTLE
    transition: RenderTransition = RenderTransition.CUT
    transition_duration_seconds: float = 0.0

    @field_validator("transition", mode="before")
    @classmethod
    def normalize_transition(cls, value: object) -> object:
        """Support legacy fade naming while normalizing to crossfade."""

        if value == "fade":
            return RenderTransition.CROSSFADE.value
        return value

    @field_validator("transition_duration_seconds")
    @classmethod
    def validate_transition_duration_seconds(cls, value: float) -> float:
        """Require finite non-negative transition durations."""

        if not math.isfinite(value):
            raise ValueError("transition_duration_seconds must be finite")
        if value < 0:
            raise ValueError("transition_duration_seconds must be zero or greater")
        return round(value, 6)

    @model_validator(mode="after")
    def validate_transition_semantics(self) -> SceneVisualTreatment:
        """Require internally coherent transition settings."""

        if self.transition is RenderTransition.CUT and not math.isclose(
            self.transition_duration_seconds,
            0.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("cut transitions must use a zero duration")
        if self.transition is RenderTransition.CROSSFADE and self.transition_duration_seconds <= 0:
            raise ValueError("crossfade transitions must use a positive duration")
        return self


class ProductionTimelineScene(CreatorOSModel):
    """One explicit paced scene interval on the final provider-neutral production timeline."""

    scene_number: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    source_asset_ref: GeneratedAsset
    trim_start_seconds: float | None = None
    trim_end_seconds: float | None = None
    caption_text: str | None = None
    caption_position: CaptionPosition = CaptionPosition.BOTTOM
    caption_max_lines: int = Field(default=2, gt=0)
    caption_style: CaptionStylePolicy = Field(default_factory=CaptionStylePolicy)
    narration_start_seconds: float | None = None
    narration_end_seconds: float | None = None
    visual_treatment: SceneVisualTreatment = Field(default_factory=SceneVisualTreatment)

    @field_validator(
        "start_seconds",
        "end_seconds",
        "duration_seconds",
        "trim_start_seconds",
        "trim_end_seconds",
        "narration_start_seconds",
        "narration_end_seconds",
    )
    @classmethod
    def validate_optional_positive_floats(cls, value: float | None, info) -> float | None:
        """Require finite non-negative timing values when supplied."""

        if value is None:
            return None
        if not math.isfinite(value):
            raise ValueError(f"{info.field_name} must be finite")
        if value < 0:
            raise ValueError(f"{info.field_name} must be zero or greater")
        return value

    @field_validator("caption_text")
    @classmethod
    def normalize_caption_text(cls, value: str | None, info) -> str | None:
        """Normalize optional caption text for timeline-only relationship metadata."""

        return _normalize_optional_string(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_scene_timing(self) -> ProductionTimelineScene:
        """Require internally consistent scene timing and asset type semantics."""

        if self.scene_number <= 0:
            raise ValueError("scene_number must be greater than zero")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        if not math.isclose(
            self.end_seconds - self.start_seconds,
            self.duration_seconds,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("duration_seconds must equal end_seconds - start_seconds")
        if self.source_asset_ref.asset_type not in {AssetType.IMAGE, AssetType.VIDEO}:
            raise ValueError("source_asset_ref.asset_type must be image or video")
        if self.trim_start_seconds is not None and self.trim_start_seconds >= self.duration_seconds:
            raise ValueError("trim_start_seconds must be smaller than duration_seconds")
        if self.trim_end_seconds is not None and self.trim_end_seconds > self.duration_seconds:
            raise ValueError("trim_end_seconds must not exceed duration_seconds")
        if (
            self.trim_start_seconds is not None
            and self.trim_end_seconds is not None
            and self.trim_end_seconds <= self.trim_start_seconds
        ):
            raise ValueError("trim_end_seconds must be greater than trim_start_seconds")
        if self.narration_start_seconds is not None and self.narration_start_seconds < self.start_seconds:
            raise ValueError("narration_start_seconds must fall within the scene interval")
        if self.narration_end_seconds is not None and self.narration_end_seconds > self.end_seconds:
            raise ValueError("narration_end_seconds must fall within the scene interval")
        if (
            self.narration_start_seconds is not None
            and self.narration_end_seconds is not None
            and self.narration_end_seconds <= self.narration_start_seconds
        ):
            raise ValueError("narration_end_seconds must be greater than narration_start_seconds")
        return self


class ProductionTimeline(CreatorOSModel):
    """Explicit provider-neutral scene pacing for final Short rendering."""

    scenes: list[ProductionTimelineScene]
    target_duration_seconds: float

    @field_validator("scenes")
    @classmethod
    def validate_scenes_present(cls, value: list[ProductionTimelineScene]) -> list[ProductionTimelineScene]:
        """Require at least one timed scene."""

        if not value:
            raise ValueError("scenes must contain at least one scene")
        return value

    @field_validator("target_duration_seconds")
    @classmethod
    def validate_target_duration_seconds(cls, value: float) -> float:
        """Require a positive finite target duration."""

        return _validate_positive_finite_float(value, field_name="target_duration_seconds")

    @model_validator(mode="after")
    def validate_scene_sequence(self) -> ProductionTimeline:
        """Require monotonic contiguous scene timing across the full timeline."""

        expected_numbers = list(range(1, len(self.scenes) + 1))
        scene_numbers = [scene.scene_number for scene in self.scenes]
        if scene_numbers != expected_numbers:
            raise ValueError("timeline scene numbers must be sequential starting at 1")

        expected_start = 0.0
        for index, scene in enumerate(self.scenes):
            if not math.isclose(scene.start_seconds, expected_start, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("timeline scenes must be contiguous and monotonically ordered")
            expected_start = scene.end_seconds
            if scene.visual_treatment.transition is RenderTransition.CROSSFADE:
                if index == len(self.scenes) - 1:
                    raise ValueError("the final timeline scene cannot transition with crossfade")
                next_scene = self.scenes[index + 1]
                if scene.visual_treatment.transition_duration_seconds >= scene.duration_seconds:
                    raise ValueError("crossfade duration must be smaller than the source scene duration")
                if scene.visual_treatment.transition_duration_seconds >= next_scene.duration_seconds:
                    raise ValueError("crossfade duration must be smaller than the destination scene duration")

        if not math.isclose(
            self.total_duration_seconds,
            self.target_duration_seconds,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("timeline total duration must equal target_duration_seconds")
        return self

    if TYPE_CHECKING:

        @property
        def total_duration_seconds(self) -> float:
            """Return the deterministic total production timeline duration."""

    else:

        @computed_field(return_type=float)
        @property
        def total_duration_seconds(self) -> float:
            """Return the deterministic total production timeline duration."""

            return round(sum(scene.duration_seconds for scene in self.scenes), 6)


class AudioCompositionPolicy(CreatorOSModel):
    """Provider-neutral audio-composition policy for initial narration handling."""

    narration_timing: NarrationTimingPolicy = NarrationTimingPolicy.FIT_TO_VIDEO


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

    @field_validator("transition", mode="before")
    @classmethod
    def normalize_transition(cls, value: object) -> object:
        """Support legacy fade naming while normalizing to crossfade."""

        if value == "fade":
            return RenderTransition.CROSSFADE.value
        return value

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
        caption_style = value.pop("caption_style", None)
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
        if caption_style is not None:
            caption_payload["style"] = caption_style
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
    production_timeline: ProductionTimeline | None = None
    narration: GeneratedAudio | None = None
    audio_policy: AudioCompositionPolicy = Field(default_factory=AudioCompositionPolicy)
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
        """Require sequential scenes, explicit production timing, and safe narration bounds."""

        scene_numbers = [scene.scene_number for scene in self.scenes]
        expected_numbers = list(range(1, len(self.scenes) + 1))
        if scene_numbers != expected_numbers:
            raise ValueError("scene numbers must be sequential starting at 1")

        if self.production_timeline is None:
            self.production_timeline = _build_legacy_production_timeline(
                scenes=self.scenes,
                narration=self.narration,
            )
        else:
            timeline_scene_numbers = [scene.scene_number for scene in self.production_timeline.scenes]
            if timeline_scene_numbers != expected_numbers:
                raise ValueError("production timeline scene numbers must match render scene numbers")

        narration_duration = (
            None if self.narration is None else self.narration.estimated_duration_seconds
        )
        if narration_duration is not None and narration_duration > self.total_duration_seconds + 1e-6:
            raise ValueError(
                "narration estimated_duration_seconds must not exceed total_duration_seconds",
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

            if self.production_timeline is not None:
                return self.production_timeline.total_duration_seconds
            return round(sum(scene.duration_seconds for scene in self.scenes), 6)


def _build_legacy_production_timeline(
    *,
    scenes: list[RenderScene],
    narration: GeneratedAudio | None,
) -> ProductionTimeline:
    """Derive one backward-compatible timeline directly from render-scene durations."""

    narration_duration = None if narration is None else narration.estimated_duration_seconds
    timeline_scenes: list[ProductionTimelineScene] = []
    current_start = 0.0
    for index, scene in enumerate(scenes):
        current_end = round(current_start + scene.duration_seconds, 6)
        if scene.video_asset_ref is not None:
            source_asset_ref = scene.video_asset_ref.model_copy(deep=True)
        elif scene.visual_asset_ref is not None:
            source_asset_ref = scene.visual_asset_ref.model_copy(deep=True)
        else:
            raise CreatorOSValidationError(
                "render scene must include one visual or video asset reference",
                code="render_scene_missing_asset",
                details={"scene_number": scene.scene_number},
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
        if index + 1 < len(scenes):
            next_scene = scenes[index + 1]
            if next_scene.video_asset_ref is not None:
                next_source_asset_type = next_scene.video_asset_ref.asset_type
            elif next_scene.visual_asset_ref is not None:
                next_source_asset_type = next_scene.visual_asset_ref.asset_type
        visual_treatment = build_default_visual_treatment(
            scene_number=scene.scene_number,
            source_asset_type=source_asset_ref.asset_type,
            next_source_asset_type=next_source_asset_type,
        )
        if scene.transition is RenderTransition.CROSSFADE and index < len(scenes) - 1:
            visual_treatment = SceneVisualTreatment(
                motion=visual_treatment.motion,
                intensity=visual_treatment.intensity,
                transition=RenderTransition.CROSSFADE,
                transition_duration_seconds=DEFAULT_CROSSFADE_DURATION_SECONDS,
            )
        timeline_scenes.append(
            ProductionTimelineScene(
                scene_number=scene.scene_number,
                start_seconds=current_start,
                end_seconds=current_end,
                duration_seconds=scene.duration_seconds,
                source_asset_ref=source_asset_ref,
                caption_text=scene.caption_text,
                caption_position=(
                    CaptionPosition.BOTTOM
                    if scene.caption is None
                    else scene.caption.position
                ),
                caption_max_lines=2 if scene.caption is None else scene.caption.max_lines,
                caption_style=(
                    CaptionStylePolicy()
                    if scene.caption is None
                    else scene.caption.style.model_copy(deep=True)
                ),
                narration_start_seconds=narration_start_seconds,
                narration_end_seconds=narration_end_seconds,
                visual_treatment=visual_treatment,
            )
        )
        current_start = current_end
    return ProductionTimeline(
        scenes=timeline_scenes,
        target_duration_seconds=round(sum(scene.duration_seconds for scene in scenes), 6),
    )


DEFAULT_CROSSFADE_DURATION_SECONDS = 0.2
_DEFAULT_STILL_IMAGE_MOTION_PATTERN = (
    VisualMotion.PUSH_IN,
    VisualMotion.PAN_RIGHT,
    VisualMotion.PUSH_IN,
    VisualMotion.PAN_LEFT,
)


def build_default_visual_treatment(
    *,
    scene_number: int,
    source_asset_type: AssetType,
    next_source_asset_type: AssetType | None,
) -> SceneVisualTreatment:
    """Build one deterministic provider-neutral visual treatment for a timeline scene."""

    if source_asset_type is AssetType.VIDEO:
        motion = VisualMotion.NONE
    else:
        motion = _DEFAULT_STILL_IMAGE_MOTION_PATTERN[(scene_number - 1) % len(_DEFAULT_STILL_IMAGE_MOTION_PATTERN)]

    transition = RenderTransition.CUT
    transition_duration_seconds = 0.0
    if source_asset_type is AssetType.IMAGE and next_source_asset_type is AssetType.IMAGE:
        transition = RenderTransition.CROSSFADE
        transition_duration_seconds = DEFAULT_CROSSFADE_DURATION_SECONDS

    return SceneVisualTreatment(
        motion=motion,
        intensity=VisualMotionIntensity.SUBTLE,
        transition=transition,
        transition_duration_seconds=transition_duration_seconds,
    )


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
    "DEFAULT_CROSSFADE_DURATION_SECONDS",
    "AudioCompositionPolicy",
    "CaptionEmphasis",
    "CaptionFontSizeProfile",
    "CaptionOverlay",
    "CaptionPosition",
    "CaptionSafeMarginProfile",
    "CaptionStylePolicy",
    "CaptionTextAlignment",
    "NarrationTimingPolicy",
    "ProductionTimeline",
    "ProductionTimelineScene",
    "RenderScene",
    "RenderTransition",
    "RenderedVideo",
    "SceneVisualTreatment",
    "ShortRenderRequest",
    "VisualMotion",
    "VisualMotionIntensity",
    "build_default_visual_treatment",
]
