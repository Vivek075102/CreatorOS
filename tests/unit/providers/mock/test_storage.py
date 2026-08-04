"""Unit tests for the CreatorOS mock storage provider."""

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers.mock import MockStorageProvider


def build_asset() -> GeneratedAsset:
    """Create a simple generated asset for storage tests."""

    return GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://assets/image.png")


def test_store_and_retrieve_work() -> None:
    """Stored assets should be retrievable through the testing helper."""

    provider = MockStorageProvider()
    asset = build_asset()

    asyncio.run(provider.store(asset))
    stored = provider.get_stored_asset(asset.id)

    assert stored is not None
    assert stored == asset


def test_returned_stored_assets_are_copies() -> None:
    """Retrieved assets should not expose internal mutable state."""

    provider = MockStorageProvider()
    asset = build_asset()

    asyncio.run(provider.store(asset))
    stored = provider.get_stored_asset(asset.id)
    assert stored is not None
    stored.metadata["changed"] = True

    refreshed = provider.get_stored_asset(asset.id)
    assert refreshed is not None
    assert refreshed.metadata == {}


def test_delete_returns_true_when_present() -> None:
    """Deleting an existing asset should return True."""

    provider = MockStorageProvider()
    asset = build_asset()
    asyncio.run(provider.store(asset))

    result = asyncio.run(provider.delete(asset.id))

    assert result.data is True


def test_delete_returns_false_when_absent() -> None:
    """Deleting a missing asset should return False."""

    provider = MockStorageProvider()

    result = asyncio.run(provider.delete("missing_asset"))

    assert result.data is False


def test_blank_asset_ids_are_rejected() -> None:
    """Blank asset identifiers should be rejected."""

    provider = MockStorageProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.delete("   "))
