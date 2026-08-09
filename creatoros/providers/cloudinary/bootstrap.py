"""Bootstrap helpers for the CreatorOS Cloudinary hosting adapter."""

from __future__ import annotations

from pathlib import Path

from creatoros.config import get_settings
from creatoros.providers.cloudinary.hosting import (
    CloudinaryAssetHostingProvider,
    _CloudinaryHostingClient,
)
from creatoros.providers.registry import ProviderRegistry


def register_cloudinary_asset_hosting_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    cloud_name: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    asset_folder: str | None = None,
    client: _CloudinaryHostingClient | None = None,
    allowed_roots: tuple[Path, ...] | None = None,
) -> CloudinaryAssetHostingProvider:
    """Register one Cloudinary asset-hosting provider without network access."""

    settings = (
        get_settings()
        if (
            cloud_name is None
            or api_key is None
            or api_secret is None
            or asset_folder is None
        )
        else None
    )
    resolved_cloud_name = settings.cloudinary_cloud_name if settings is not None and cloud_name is None else cloud_name
    resolved_api_key = settings.cloudinary_api_key if settings is not None and api_key is None else api_key
    resolved_api_secret = (
        settings.cloudinary_api_secret if settings is not None and api_secret is None else api_secret
    )
    resolved_asset_folder = (
        settings.cloudinary_asset_folder if settings is not None and asset_folder is None else asset_folder
    )
    provider = CloudinaryAssetHostingProvider(
        cloud_name=resolved_cloud_name,
        api_key=resolved_api_key,
        api_secret=resolved_api_secret,
        asset_folder=resolved_asset_folder or "creatoros",
        client=client,
        allowed_roots=allowed_roots,
    )
    registry.register(provider, replace=replace)
    return provider


__all__ = ["register_cloudinary_asset_hosting_provider"]
