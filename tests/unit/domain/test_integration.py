"""Unit tests for CreatorOS provider handoff domain models."""

import pytest
from pydantic import ValidationError

from creatoros.domain import (
    AssetType,
    ContentPlatform,
    GeneratedAsset,
    NarrationTrack,
    PerformanceReport,
    PublishedPost,
    PublishingPackage,
)


def test_integration_models_generate_expected_id_prefixes() -> None:
    """Integration handoff models should generate stable identifier prefixes."""

    asset = GeneratedAsset(asset_type=AssetType.IMAGE, uri="https://example.com/image.png")
    narration = NarrationTrack(uri="https://example.com/audio.mp3", duration_seconds=12.5)
    package = PublishingPackage(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        title="Boss Guide",
        description="Fast strategy breakdown.",
    )
    post = PublishedPost(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        external_id="abc123",
        url="https://example.com/post/abc123",
    )
    report = PerformanceReport(post_id="published_post_123", metrics={"views": 1000})

    assert asset.id.startswith("asset_")
    assert narration.id.startswith("narration_")
    assert package.id.startswith("publishing_package_")
    assert post.id.startswith("published_post_")
    assert report.id.startswith("performance_report_")


def test_integration_models_do_not_share_mutable_metadata_defaults() -> None:
    """Metadata dictionaries should not be shared across model instances."""

    first = GeneratedAsset(asset_type=AssetType.IMAGE, uri="https://example.com/first.png")
    second = GeneratedAsset(asset_type=AssetType.IMAGE, uri="https://example.com/second.png")

    first.metadata["quality"] = "high"

    assert second.metadata == {}


def test_integration_models_reject_blank_required_strings() -> None:
    """Required string fields should reject blank input."""

    with pytest.raises(ValidationError):
        GeneratedAsset(asset_type=AssetType.IMAGE, uri="   ")

    with pytest.raises(ValidationError):
        NarrationTrack(uri="   ", duration_seconds=8)

    with pytest.raises(ValidationError):
        PublishingPackage(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            title="Boss Guide",
            description="   ",
        )

    with pytest.raises(ValidationError):
        PublishedPost(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            external_id="   ",
            url="https://example.com/post",
        )

    with pytest.raises(ValidationError):
        PerformanceReport(post_id="   ", metrics={})


def test_integration_models_validate_positive_duration_values() -> None:
    """Duration-bearing placeholder models should require positive values."""

    with pytest.raises(ValidationError):
        NarrationTrack(uri="https://example.com/audio.mp3", duration_seconds=0)


def test_integration_models_round_trip_predictably() -> None:
    """Integration models should serialize and restore predictably."""

    original = PublishedPost(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        external_id="abc123",
        url="https://example.com/post/abc123",
        metadata={"status": "draft"},
    )

    restored = PublishedPost.model_validate(original.model_dump())

    assert restored == original
