"""Provider-neutral media-generation request and result contracts for CreatorOS."""

from __future__ import annotations

import math

from pydantic import Field, field_validator, model_validator

from creatoros.domain import AssetType, CreatorOSModel, GeneratedAsset


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


class ImageGenerationRequest(CreatorOSModel):
    """Provider-neutral request for future image-generation providers."""

    prompt: str
    width: int = Field(default=1024, gt=0)
    height: int = Field(default=1024, gt=0)
    negative_prompt: str | None = None
    seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Trim and reject blank image prompts."""

        return _validate_non_blank(value, field_name="prompt")

    @field_validator("negative_prompt")
    @classmethod
    def validate_negative_prompt(cls, value: str | None) -> str | None:
        """Normalize optional negative prompts."""

        return _normalize_optional_string(value, field_name="negative_prompt")


class TTSGenerationRequest(CreatorOSModel):
    """Provider-neutral request for future speech-generation providers."""

    text: str
    voice: str | None = None
    language: str | None = None
    speed: float | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Trim and reject blank narration text."""

        return _validate_non_blank(value, field_name="text")

    @field_validator("voice", "language")
    @classmethod
    def validate_optional_strings(cls, value: str | None, info) -> str | None:
        """Normalize optional provider-neutral voice settings."""

        return _normalize_optional_string(value, field_name=info.field_name)

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, value: float | None) -> float | None:
        """Require positive finite speech speed values when supplied."""

        if value is None:
            return None
        return _validate_positive_finite_float(value, field_name="speed")


class VideoGenerationRequest(CreatorOSModel):
    """Provider-neutral request for future video-generation providers."""

    prompt: str
    duration_seconds: float
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = None
    negative_prompt: str | None = None
    seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Trim and reject blank video prompts."""

        return _validate_non_blank(value, field_name="prompt")

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive finite video durations."""

        return _validate_positive_finite_float(value, field_name="duration_seconds")

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, value: float | None) -> float | None:
        """Require positive finite frame-rate values when supplied."""

        if value is None:
            return None
        return _validate_positive_finite_float(value, field_name="fps")

    @field_validator("negative_prompt")
    @classmethod
    def validate_negative_prompt(cls, value: str | None) -> str | None:
        """Normalize optional negative prompts."""

        return _normalize_optional_string(value, field_name="negative_prompt")


class GeneratedImage(CreatorOSModel):
    """Provider-neutral image-generation result for downstream media workflows."""

    artifact: GeneratedAsset
    provider_name: str
    model: str
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    payload_bytes: bytes | None = Field(default=None, exclude=True, repr=False)

    @field_validator("provider_name", "model", "mime_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required result identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        """Normalize optional request identifiers."""

        return _normalize_optional_string(value, field_name="request_id")

    @field_validator("payload_bytes")
    @classmethod
    def validate_payload_bytes(cls, value: bytes | None) -> bytes | None:
        """Require non-empty payload bytes when a payload is present."""

        if value is None:
            return None
        if not value:
            raise ValueError("payload_bytes must not be empty")
        return bytes(value)

    @model_validator(mode="after")
    def validate_artifact_type(self) -> GeneratedImage:
        """Require an image asset reference."""

        if self.artifact.asset_type is not AssetType.IMAGE:
            raise ValueError("artifact.asset_type must be image")
        return self


class GeneratedAudio(CreatorOSModel):
    """Provider-neutral speech-generation result for downstream media workflows."""

    artifact: GeneratedAsset
    provider_name: str
    model: str
    mime_type: str
    voice: str | None = None
    language: str | None = None
    estimated_duration_seconds: float | None = None
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    payload_bytes: bytes | None = Field(default=None, exclude=True, repr=False)

    @field_validator("provider_name", "model", "mime_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required result identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("voice", "language", "request_id")
    @classmethod
    def validate_optional_strings(cls, value: str | None, info) -> str | None:
        """Normalize optional audio-result identifiers."""

        return _normalize_optional_string(value, field_name=info.field_name)

    @field_validator("estimated_duration_seconds")
    @classmethod
    def validate_estimated_duration_seconds(cls, value: float | None) -> float | None:
        """Require positive finite estimated durations when supplied."""

        if value is None:
            return None
        return _validate_positive_finite_float(value, field_name="estimated_duration_seconds")

    @field_validator("payload_bytes")
    @classmethod
    def validate_payload_bytes(cls, value: bytes | None) -> bytes | None:
        """Require non-empty payload bytes when a payload is present."""

        if value is None:
            return None
        if not value:
            raise ValueError("payload_bytes must not be empty")
        return bytes(value)

    @model_validator(mode="after")
    def validate_artifact_type(self) -> GeneratedAudio:
        """Require an audio-oriented asset reference."""

        if self.artifact.asset_type not in {AssetType.AUDIO, AssetType.NARRATION}:
            raise ValueError("artifact.asset_type must be audio or narration")
        return self


class GeneratedVideo(CreatorOSModel):
    """Provider-neutral video-generation result for downstream media workflows."""

    artifact: GeneratedAsset
    provider_name: str
    model: str
    mime_type: str
    duration_seconds: float
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = None
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    payload_bytes: bytes | None = Field(default=None, exclude=True, repr=False)

    @field_validator("provider_name", "model", "mime_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required result identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive finite video durations."""

        return _validate_positive_finite_float(value, field_name="duration_seconds")

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, value: float | None) -> float | None:
        """Require positive finite frame-rate values when supplied."""

        if value is None:
            return None
        return _validate_positive_finite_float(value, field_name="fps")

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        """Normalize optional request identifiers."""

        return _normalize_optional_string(value, field_name="request_id")

    @field_validator("payload_bytes")
    @classmethod
    def validate_payload_bytes(cls, value: bytes | None) -> bytes | None:
        """Require non-empty payload bytes when a payload is present."""

        if value is None:
            return None
        if not value:
            raise ValueError("payload_bytes must not be empty")
        return bytes(value)

    @model_validator(mode="after")
    def validate_artifact_type(self) -> GeneratedVideo:
        """Require a video asset reference."""

        if self.artifact.asset_type is not AssetType.VIDEO:
            raise ValueError("artifact.asset_type must be video")
        return self


__all__ = [
    "GeneratedAudio",
    "GeneratedImage",
    "GeneratedVideo",
    "ImageGenerationRequest",
    "TTSGenerationRequest",
    "VideoGenerationRequest",
]
