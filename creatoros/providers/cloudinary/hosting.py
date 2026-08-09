"""Cloudinary-backed asset-hosting provider for CreatorOS."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from creatoros.config import get_settings
from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset, HostedAsset
from creatoros.observability import get_logger
from creatoros.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
)
from creatoros.providers.contracts import AssetHostingProvider

DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME = "cloudinary"
_CLOUDINARY_HOSTING_PROVIDER_TYPE = "hosting"
_SUPPORTED_IMAGE_SUFFIXES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_SAFE_PUBLIC_ID_PART_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_LOGGER = get_logger("providers.cloudinary.hosting")


class _CloudinaryHostingClient(Protocol):
    """Minimal Cloudinary client boundary used for upload and delete tests."""

    def upload(self, file: str, **kwargs: object) -> dict[str, object]:
        """Upload a local file path and return the normalized Cloudinary response."""

    def destroy(self, public_id: str, **kwargs: object) -> dict[str, object]:
        """Delete one hosted Cloudinary asset by public identifier."""


class _CloudinaryUploaderClient:
    """Thin wrapper around the official Cloudinary uploader module."""

    def __init__(self, uploader_module: Any) -> None:
        self._uploader_module = uploader_module

    def upload(self, file: str, **kwargs: object) -> dict[str, object]:
        """Delegate one upload call to the official uploader implementation."""

        response = self._uploader_module.upload(file, **kwargs)
        if not isinstance(response, dict):
            raise ProviderResponseError(
                "Cloudinary upload response could not be normalized safely",
                code="provider_response_invalid",
                details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
            )
        return dict(response)

    def destroy(self, public_id: str, **kwargs: object) -> dict[str, object]:
        """Delegate one delete call to the official uploader implementation."""

        response = self._uploader_module.destroy(public_id, **kwargs)
        if not isinstance(response, dict):
            raise ProviderResponseError(
                "Cloudinary delete response could not be normalized safely",
                code="provider_response_invalid",
                details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
            )
        return dict(response)


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional strings to stripped values or ``None``."""

    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    """Require one non-blank string value for provider configuration."""

    normalized_value = _normalize_optional_string(value)
    if normalized_value is None:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={
                "field": field_name,
                "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
            },
        )
    return normalized_value


def _sanitize_public_id_part(value: str) -> str:
    """Normalize one public-ID path segment into a deterministic safe token."""

    stripped_value = value.strip()
    sanitized = _SAFE_PUBLIC_ID_PART_PATTERN.sub("-", stripped_value).strip("-")
    return sanitized or "default"


def _safe_run_scope(context: ProviderRequestContext | None) -> str:
    """Return a deterministic run scope for provider public IDs."""

    if context is None:
        return "unscoped"
    raw_run_id = context.metadata.get("run_id")
    if isinstance(raw_run_id, str) and raw_run_id.strip():
        return _sanitize_public_id_part(raw_run_id)
    return "unscoped"


def _normalize_allowed_roots(allowed_roots: tuple[Path, ...] | None) -> tuple[Path, ...]:
    """Normalize allowed roots to resolved absolute paths."""

    if allowed_roots is not None:
        return tuple(path.resolve() for path in allowed_roots)

    settings = get_settings()
    return (settings.artifact_root.resolve(), settings.assets_dir.resolve())


def _ensure_within_allowed_roots(path: Path, *, allowed_roots: tuple[Path, ...]) -> None:
    """Require a local file path to remain inside one configured CreatorOS root."""

    resolved_path = path.resolve()
    for root in allowed_roots:
        try:
            resolved_path.relative_to(root)
            return
        except ValueError:
            continue

    raise CreatorOSValidationError(
        "asset path must remain inside configured CreatorOS roots",
        code="provider_invalid_input",
        details={
            "field": "asset.uri",
            "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
        },
    )


def _normalize_https_url(value: object) -> str:
    """Require one valid Cloudinary HTTPS delivery URL."""

    if not isinstance(value, str):
        raise ProviderResponseError(
            "Cloudinary upload response did not include a usable secure URL",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
        )
    normalized_value = value.strip()
    parsed = urlsplit(normalized_value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProviderResponseError(
            "Cloudinary upload response did not include a usable secure URL",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
        )
    return normalized_value


def _normalize_public_id(value: object) -> str:
    """Require one valid Cloudinary public ID."""

    if not isinstance(value, str) or not value.strip():
        raise ProviderResponseError(
            "Cloudinary upload response did not include a usable public ID",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
        )
    return value.strip()


class CloudinaryAssetHostingProvider(AssetHostingProvider):
    """Host local generated images through the official Cloudinary SDK."""

    def __init__(
        self,
        *,
        cloud_name: str | None,
        api_key: str | None,
        api_secret: str | None,
        asset_folder: str = "creatoros",
        client: _CloudinaryHostingClient | None = None,
        allowed_roots: tuple[Path, ...] | None = None,
    ) -> None:
        self._cloud_name = _require_non_blank(cloud_name, field_name="cloud_name")
        self._api_key = _require_non_blank(api_key, field_name="api_key")
        self._api_secret = _require_non_blank(api_secret, field_name="api_secret")
        self._asset_folder = _require_non_blank(asset_folder, field_name="asset_folder").strip("/")
        self._allowed_roots = _normalize_allowed_roots(allowed_roots)
        self._client = client
        self._info = ProviderInfo(
            name=DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
            provider_type=_CLOUDINARY_HOSTING_PROVIDER_TYPE,
            capabilities={ProviderCapability.ASSET_HOSTING},
            version="1.0",
            metadata={"delivery": "https", "provider_api": "upload.destroy"},
        )

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the Cloudinary adapter."""

        return self._info.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return local configuration readiness without live network access."""

        return all(
            (
                bool(self._cloud_name),
                bool(self._api_key),
                bool(self._api_secret),
                bool(self._asset_folder),
            )
        )

    async def host(
        self,
        asset: GeneratedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[HostedAsset]:
        """Upload one local generated image and return its public HTTPS reference."""

        source_asset = asset.model_copy(deep=True)
        local_path, mime_type = self._validate_source_asset(source_asset)
        public_id = self._build_public_id(source_asset, context=context)
        client = self._get_client()
        request_timeout = None if context is None else context.timeout_seconds

        _LOGGER.info(
            "provider_asset_hosting_started",
            provider_name=self.info.name,
            asset_id=source_asset.id,
            asset_type=source_asset.asset_type.value,
        )

        try:
            response = client.upload(
                str(local_path),
                public_id=public_id,
                overwrite=False,
                resource_type="image",
                folder=self._asset_folder,
                timeout=request_timeout,
            )
        except Exception as error:
            translated_error = self._translate_error(error)
            _LOGGER.warning(
                "provider_asset_hosting_failed",
                provider_name=self.info.name,
                asset_id=source_asset.id,
                error_code=translated_error.code,
            )
            raise translated_error from error

        asset_id = response.get("asset_id")
        hosted_asset = HostedAsset(
            source_asset=source_asset,
            public_url=_normalize_https_url(response.get("secure_url")),
            provider_name=self.info.name,
            provider_asset_id=_normalize_public_id(response.get("public_id")),
            mime_type=mime_type,
            request_id=_normalize_optional_string(asset_id) if isinstance(asset_id, str) else None,
            metadata=self._build_safe_metadata(response),
        )
        _LOGGER.info(
            "provider_asset_hosting_completed",
            provider_name=self.info.name,
            asset_id=source_asset.id,
            provider_asset_id=hosted_asset.provider_asset_id,
            success=True,
        )
        return ProviderResult[HostedAsset](
            data=hosted_asset,
            provider=self.info,
            request_id=hosted_asset.request_id,
            metadata={"overwrite": False, "resource_type": "image"},
        )

    async def delete(
        self,
        hosted_asset: HostedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[bool]:
        """Delete one previously hosted Cloudinary image by public ID."""

        del context
        client = self._get_client()

        try:
            response = client.destroy(
                hosted_asset.provider_asset_id,
                resource_type="image",
            )
        except Exception as error:
            raise self._translate_error(error) from error

        result = response.get("result")
        if not isinstance(result, str) or not result.strip():
            raise ProviderResponseError(
                "Cloudinary delete response could not be normalized safely",
                code="provider_response_invalid",
                details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
            )

        normalized_result = result.strip().lower()
        return ProviderResult[bool](
            data=normalized_result == "ok",
            provider=self.info,
            metadata={"resource_type": "image", "result": normalized_result},
        )

    def _validate_source_asset(self, asset: GeneratedAsset) -> tuple[Path, str]:
        """Validate that the source asset is one supported local image file."""

        if asset.asset_type is not AssetType.IMAGE:
            raise CreatorOSValidationError(
                "Cloudinary hosting currently supports image assets only",
                code="provider_invalid_input",
                details={
                    "field": "asset.asset_type",
                    "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
                },
            )

        local_path = Path(asset.uri)
        if not local_path.is_absolute():
            local_path = local_path.resolve()
        if not local_path.exists() or not local_path.is_file():
            raise CreatorOSValidationError(
                "asset.uri must point to an existing local file",
                code="provider_invalid_input",
                details={
                    "field": "asset.uri",
                    "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
                },
            )
        if local_path.stat().st_size <= 0:
            raise CreatorOSValidationError(
                "asset.uri must point to a non-empty local file",
                code="provider_invalid_input",
                details={
                    "field": "asset.uri",
                    "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
                },
            )

        suffix = local_path.suffix.lower()
        mime_type = _SUPPORTED_IMAGE_SUFFIXES.get(suffix)
        if mime_type is None:
            raise CreatorOSValidationError(
                "asset.uri must use a supported image file extension",
                code="provider_invalid_input",
                details={
                    "field": "asset.uri",
                    "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
                },
            )

        _ensure_within_allowed_roots(local_path, allowed_roots=self._allowed_roots)
        return local_path, mime_type

    def _build_public_id(
        self,
        asset: GeneratedAsset,
        *,
        context: ProviderRequestContext | None,
    ) -> str:
        """Build one deterministic run-scoped Cloudinary public ID."""

        run_scope = _safe_run_scope(context)
        asset_id = _sanitize_public_id_part(asset.id)
        return f"{self._asset_folder}/{run_scope}/{asset_id}"

    def _build_safe_metadata(self, response: dict[str, object]) -> dict[str, object]:
        """Return one safe subset of Cloudinary response metadata."""

        metadata: dict[str, object] = {}
        for key in ("resource_type", "format", "width", "height", "bytes"):
            value = response.get(key)
            if isinstance(value, str | int):
                metadata[key] = value
        metadata["provider_reference_kind"] = "public_https_url"
        return metadata

    def _get_client(self) -> _CloudinaryHostingClient:
        """Return the injected Cloudinary client or construct the SDK wrapper lazily."""

        if self._client is not None:
            return self._client

        try:
            import cloudinary  # type: ignore[import-not-found]
            from cloudinary import uploader  # type: ignore[import-not-found]
        except ImportError as error:
            raise ProviderUnavailableError(
                "Cloudinary SDK is not installed",
                code="provider_unavailable",
                details={"provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME},
            ) from error

        cloudinary.config(
            cloud_name=self._cloud_name,
            api_key=self._api_key,
            api_secret=self._api_secret,
            secure=True,
        )
        self._client = _CloudinaryUploaderClient(uploader)
        return self._client

    def _translate_error(
        self,
        error: Exception,
    ) -> ProviderAuthenticationError | ProviderRateLimitError | ProviderResponseError | ProviderUnavailableError:
        """Translate Cloudinary-side failures into typed CreatorOS provider errors."""

        safe_details: dict[str, object] = {
            "provider_name": DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME
        }
        message = str(error).lower()
        error_name = type(error).__name__.lower()

        if "auth" in message or "auth" in error_name or "unauthorized" in message:
            return ProviderAuthenticationError(
                "Cloudinary authentication failed",
                code="provider_authentication_failed",
                details=safe_details,
                retryable=False,
            )
        if "rate" in message or "rate" in error_name or "quota" in message:
            return ProviderRateLimitError(
                "Cloudinary rate limit encountered",
                code="provider_rate_limited",
                details=safe_details,
            )
        if "network" in message or "timeout" in message or "connection" in message:
            return ProviderUnavailableError(
                "Cloudinary service is unavailable",
                code="provider_unavailable",
                details=safe_details,
            )
        if isinstance(error, ProviderResponseError):
            return error
        return ProviderResponseError(
            "Cloudinary response could not be normalized safely",
            code="provider_response_invalid",
            details=safe_details,
        )


__all__ = [
    "DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME",
    "CloudinaryAssetHostingProvider",
]
