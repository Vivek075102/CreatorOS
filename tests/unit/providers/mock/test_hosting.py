"""Unit tests for the deterministic mock asset-hosting provider."""

from __future__ import annotations

import asyncio

from creatoros.domain import AssetType, GeneratedAsset, HostedAsset
from creatoros.providers import AssetHostingProvider
from creatoros.providers.mock import MockAssetHostingProvider


def build_asset(uri: str = "C:/GamingAIFactory/artifacts/run_001/images/scene.png") -> GeneratedAsset:
    """Create a deterministic generated image asset for hosting tests."""

    return GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri=uri,
        metadata={"role": "scene_image"},
    )


def test_mock_hosting_provider_satisfies_runtime_protocol() -> None:
    """The mock hosting adapter should satisfy the provider-neutral protocol."""

    provider = MockAssetHostingProvider()

    assert isinstance(provider, AssetHostingProvider)


def test_mock_hosting_provider_returns_deterministic_https_urls() -> None:
    """The same asset should always produce the same fake public URL."""

    provider = MockAssetHostingProvider()
    asset = build_asset()

    first = asyncio.run(provider.host(asset))
    second = asyncio.run(provider.host(asset))

    assert first.data.public_url == second.data.public_url
    assert first.data.public_url.startswith("https://example.invalid/creatoros/")
    assert first.data.provider_asset_id == second.data.provider_asset_id


def test_mock_hosting_provider_varies_url_by_asset_identity() -> None:
    """Different assets should produce different deterministic public URLs."""

    provider = MockAssetHostingProvider()

    first = asyncio.run(provider.host(build_asset("C:/GamingAIFactory/artifacts/run_001/images/scene_a.png")))
    second = asyncio.run(provider.host(build_asset("C:/GamingAIFactory/artifacts/run_001/images/scene_b.png")))

    assert first.data.public_url != second.data.public_url


def test_mock_hosting_provider_preserves_source_asset_without_mutation() -> None:
    """Hosting should preserve the caller's source asset model."""

    provider = MockAssetHostingProvider()
    asset = build_asset()
    before = asset.model_dump()

    result = asyncio.run(provider.host(asset))

    assert asset.model_dump() == before
    assert isinstance(result.data, HostedAsset)
    assert result.data.source_asset == asset


def test_mock_delete_is_safe_and_deterministic() -> None:
    """Delete should be a deterministic local no-op with a stable boolean result."""

    provider = MockAssetHostingProvider()
    hosted_asset = asyncio.run(provider.host(build_asset())).data

    result = asyncio.run(provider.delete(hosted_asset))

    assert result.data is True
