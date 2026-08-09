"""Milestone 1 provider handoff models for CreatorOS integration boundaries."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, field_validator

from creatoros.domain.base import CreatorOSModel, generate_id
from creatoros.domain.enums import AssetType, ContentPlatform


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Reject blank values for required textual fields."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GeneratedAsset(CreatorOSModel):
    """Minimal generated asset contract used for provider handoff."""

    id: str = Field(default_factory=lambda: generate_id("asset"))
    asset_type: AssetType
    uri: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str, info) -> str:
        """Reject blank asset URIs."""

        return _validate_non_blank(value, field_name=info.field_name)


class HostedAsset(CreatorOSModel):
    """Public hosted asset contract returned by provider-neutral hosting adapters."""

    id: str = Field(default_factory=lambda: generate_id("hosted_asset"))
    source_asset: GeneratedAsset
    public_url: str
    provider_name: str
    provider_asset_id: str
    mime_type: str | None = None
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("source_asset", mode="before")
    @classmethod
    def copy_source_asset(cls, value: object) -> GeneratedAsset:
        """Deep-copy the original generated asset to preserve caller ownership."""

        if isinstance(value, GeneratedAsset):
            return value.model_copy(deep=True)
        if isinstance(value, dict):
            return GeneratedAsset.model_validate(value)
        raise TypeError("source_asset must be a GeneratedAsset")

    @field_validator("public_url", "provider_name", "provider_asset_id")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Reject blank required hosting fields."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("public_url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        """Require a public HTTPS URL for hosted assets."""

        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("public_url must be a valid HTTPS URL")
        return value

    @field_validator("mime_type", "request_id")
    @classmethod
    def normalize_optional_strings(cls, value: str | None, info) -> str | None:
        """Normalize optional blank strings to ``None``."""

        if value is None:
            return None
        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, object]) -> dict[str, object]:
        """Reject binary payloads from hosted-asset metadata."""

        def contains_binary(payload: object) -> bool:
            if isinstance(payload, bytes | bytearray | memoryview):
                return True
            if isinstance(payload, dict):
                return any(contains_binary(item) for item in payload.values())
            if isinstance(payload, list | tuple | set):
                return any(contains_binary(item) for item in payload)
            return False

        if contains_binary(value):
            raise ValueError("metadata must not contain binary payloads")
        return dict(value)


class NarrationTrack(CreatorOSModel):
    """Minimal narration contract used for provider handoff."""

    id: str = Field(default_factory=lambda: generate_id("narration"))
    uri: str
    duration_seconds: float
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str, info) -> str:
        """Reject blank narration URIs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive narration durations."""

        if value <= 0:
            raise ValueError("duration_seconds must be greater than zero")
        return value


class PublishingPackage(CreatorOSModel):
    """Minimal publishing payload used at the provider boundary."""

    id: str = Field(default_factory=lambda: generate_id("publishing_package"))
    platform: ContentPlatform
    title: str
    description: str
    asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("title", "description")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Reject blank publishing package fields."""

        return _validate_non_blank(value, field_name=info.field_name)


class PublishedPost(CreatorOSModel):
    """Minimal published post contract returned by publishing providers."""

    id: str = Field(default_factory=lambda: generate_id("published_post"))
    platform: ContentPlatform
    external_id: str
    url: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("external_id", "url")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Reject blank published post fields."""

        return _validate_non_blank(value, field_name=info.field_name)


class PerformanceReport(CreatorOSModel):
    """Minimal analytics payload returned by performance providers."""

    id: str = Field(default_factory=lambda: generate_id("performance_report"))
    post_id: str
    metrics: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("post_id")
    @classmethod
    def validate_post_id(cls, value: str, info) -> str:
        """Reject blank post identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)


__all__ = [
    "GeneratedAsset",
    "HostedAsset",
    "NarrationTrack",
    "PerformanceReport",
    "PublishedPost",
    "PublishingPackage",
]
