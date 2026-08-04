"""Unit tests for the CreatorOS mock publishing provider."""

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError, ProviderNotFoundError
from creatoros.domain import ContentPlatform, PublishingPackage
from creatoros.providers.mock import MockPublishingProvider


def build_package(*, asset_ids: list[str] | None = None) -> PublishingPackage:
    """Create a simple publishing package for mock publishing tests."""

    return PublishingPackage(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        title="Boss Guide",
        description="Fast strategy breakdown.",
        asset_ids=["asset_123"] if asset_ids is None else asset_ids,
    )


def test_publish_returns_published_post() -> None:
    """Publishing should return a deterministic PublishedPost."""

    provider = MockPublishingProvider()

    result = asyncio.run(provider.publish(build_package()))

    assert result.data.url.startswith("mock://published/")


def test_external_ids_use_expected_prefix() -> None:
    """Published external identifiers should use the mock_post prefix."""

    provider = MockPublishingProvider()

    result = asyncio.run(provider.publish(build_package()))

    assert result.data.external_id.startswith("mock_post_")


def test_status_can_be_retrieved() -> None:
    """Stored publish status should be retrievable by external identifier."""

    provider = MockPublishingProvider()
    publish_result = asyncio.run(provider.publish(build_package()))

    status_result = asyncio.run(provider.get_status(publish_result.data.external_id))

    assert status_result.data == "published"


def test_package_without_asset_ids_is_rejected() -> None:
    """Publishing requires at least one asset identifier."""

    provider = MockPublishingProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.publish(build_package(asset_ids=[])))


def test_missing_status_raises_typed_error() -> None:
    """Missing publish statuses should raise a typed lookup error."""

    provider = MockPublishingProvider()

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(provider.get_status("missing_post"))
