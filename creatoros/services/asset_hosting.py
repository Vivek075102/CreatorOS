"""Application-layer service for provider-neutral asset hosting."""

from __future__ import annotations

from creatoros.config import Settings, get_settings
from creatoros.core import CreatorOSValidationError, ProviderTypeMismatchError
from creatoros.domain import GeneratedAsset, HostedAsset
from creatoros.observability import get_logger
from creatoros.providers import AssetHostingProvider, ProviderRegistry, ProviderRequestContext
from creatoros.providers.mock import create_mock_provider_registry


class AssetHostingService:
    """Resolve and execute provider-neutral asset hosting operations."""

    def __init__(self, provider_registry: ProviderRegistry, settings: Settings) -> None:
        if not isinstance(provider_registry, ProviderRegistry):
            raise CreatorOSValidationError(
                "provider_registry must be a ProviderRegistry",
                code="service_invalid_dependency",
                details={"dependency": "provider_registry"},
            )
        if not isinstance(settings, Settings):
            raise CreatorOSValidationError(
                "settings must be a Settings instance",
                code="service_invalid_dependency",
                details={"dependency": "settings"},
            )
        self.provider_registry = provider_registry
        self.settings = settings
        self.logger = get_logger("services.asset_hosting")

    async def host_asset(
        self,
        asset: GeneratedAsset,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> HostedAsset:
        """Host one generated asset through the resolved hosting provider."""

        provider = self._resolve_provider(provider_name)
        self.logger.info(
            "asset_hosting_started",
            provider_name=provider.info.name,
            asset_id=asset.id,
            asset_type=asset.asset_type.value,
        )
        result = await provider.host(asset, context=context)
        self.logger.info(
            "asset_hosting_completed",
            provider_name=result.data.provider_name,
            asset_id=result.data.source_asset.id,
            provider_asset_id=result.data.provider_asset_id,
            success=True,
        )
        return result.data.model_copy(deep=True)

    async def delete_hosted_asset(
        self,
        hosted_asset: HostedAsset,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> bool:
        """Delete one hosted asset through the resolved hosting provider."""

        resolved_provider_name = provider_name or hosted_asset.provider_name
        provider = self._resolve_provider(resolved_provider_name)
        self.logger.info(
            "asset_hosting_delete_started",
            provider_name=provider.info.name,
            provider_asset_id=hosted_asset.provider_asset_id,
        )
        result = await provider.delete(hosted_asset, context=context)
        self.logger.info(
            "asset_hosting_delete_completed",
            provider_name=provider.info.name,
            provider_asset_id=hosted_asset.provider_asset_id,
            deleted=result.data,
            success=True,
        )
        return bool(result.data)

    def _resolve_provider(self, provider_name: str | None) -> AssetHostingProvider:
        """Resolve either the explicit or configured default hosting provider."""

        resolved_provider_name = (
            self.settings.default_asset_hosting_provider if provider_name is None else provider_name
        )
        provider = self.provider_registry.get("hosting", resolved_provider_name)
        if not isinstance(provider, AssetHostingProvider):
            raise ProviderTypeMismatchError(
                "hosting",
                resolved_provider_name.strip().lower(),
                "AssetHostingProvider",
            )
        return provider


def create_asset_hosting_service(
    *,
    provider_registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
) -> AssetHostingService:
    """Create a safe default asset-hosting service using the mock provider registry."""

    resolved_settings = get_settings() if settings is None else settings
    resolved_provider_registry = create_mock_provider_registry() if provider_registry is None else provider_registry
    return AssetHostingService(resolved_provider_registry, resolved_settings)


__all__ = ["AssetHostingService", "create_asset_hosting_service"]
