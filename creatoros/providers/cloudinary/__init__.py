"""Cloudinary asset-hosting provider implementation for CreatorOS."""

from creatoros.providers.cloudinary.bootstrap import register_cloudinary_asset_hosting_provider
from creatoros.providers.cloudinary.hosting import (
    DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
    CloudinaryAssetHostingProvider,
)

__all__ = [
    "DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME",
    "CloudinaryAssetHostingProvider",
    "register_cloudinary_asset_hosting_provider",
]
