"""Deterministic mock storage provider for CreatorOS."""

from __future__ import annotations

from creatoros.core import CreatorOSValidationError
from creatoros.domain import GeneratedAsset, generate_id
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name},
        )
    return normalized_value


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class MockStorageProvider(MockProviderBase):
    """Deterministic in-memory storage provider for local testing."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="storage",
            capabilities={ProviderCapability.STORAGE},
            is_healthy=is_healthy,
        )
        self._assets: dict[str, GeneratedAsset] = {}

    async def store(
        self,
        asset: GeneratedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Store and return a copied generated asset."""

        stored_asset = asset.model_copy(deep=True)
        self._assets[stored_asset.id] = stored_asset
        return ProviderResult[GeneratedAsset](
            data=stored_asset.model_copy(deep=True),
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )

    async def delete(
        self,
        asset_id: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[bool]:
        """Delete a stored asset by identifier and report whether it was present."""

        normalized_asset_id = _validate_non_blank(asset_id, field_name="asset_id")
        deleted = self._assets.pop(normalized_asset_id, None) is not None
        return ProviderResult[bool](
            data=deleted,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )

    def get_stored_asset(self, asset_id: str) -> GeneratedAsset | None:
        """Return a copied stored asset for tests and local development."""

        stored_asset = self._assets.get(asset_id)
        if stored_asset is None:
            return None
        return stored_asset.model_copy(deep=True)


__all__ = ["MockStorageProvider"]
