"""Deterministic mock asset-hosting provider for CreatorOS."""

from __future__ import annotations

import hashlib

from creatoros.domain import AssetType, GeneratedAsset, HostedAsset
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
)
from creatoros.providers.contracts import AssetHostingProvider
from creatoros.providers.mock.base import MockProviderBase

_MOCK_HOSTING_PROVIDER_NAME = "mock"
_MOCK_HOSTING_PROVIDER_TYPE = "hosting"


def _build_digest(asset: GeneratedAsset) -> str:
    """Return a deterministic digest for one hosted asset response."""

    payload = (
        f"{asset.id}|{asset.asset_type.value}|{asset.uri}|"
        f"{sorted(asset.metadata.items(), key=lambda item: item[0])}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class MockAssetHostingProvider(MockProviderBase, AssetHostingProvider):
    """Return deterministic fake HTTPS URLs for provider-neutral hosting tests."""

    def __init__(self) -> None:
        super().__init__(
            name=_MOCK_HOSTING_PROVIDER_NAME,
            provider_type=_MOCK_HOSTING_PROVIDER_TYPE,
            capabilities={ProviderCapability.ASSET_HOSTING},
        )

    async def host(
        self,
        asset: GeneratedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[HostedAsset]:
        """Return a deterministic fake hosted asset without network access."""

        del context
        digest = _build_digest(asset)
        suffix = ".png" if asset.asset_type is AssetType.IMAGE else ""
        hosted_asset = HostedAsset(
            source_asset=asset,
            public_url=f"https://example.invalid/creatoros/{digest}{suffix}",
            provider_name=self.info.name,
            provider_asset_id=f"creatoros/{digest}",
            mime_type="image/png" if asset.asset_type is AssetType.IMAGE else None,
            metadata={"provider_reference_kind": "mock_public_url"},
        )
        return ProviderResult[HostedAsset](data=hosted_asset, provider=self.info)

    async def delete(
        self,
        hosted_asset: HostedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[bool]:
        """Return a deterministic delete result without mutating external state."""

        del context
        return ProviderResult[bool](
            data=bool(hosted_asset.provider_asset_id.strip()),
            provider=self.info,
        )


__all__ = ["MockAssetHostingProvider"]
