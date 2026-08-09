"""Unit tests for the Cloudinary asset-hosting provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    AssetHostingProvider,
    ProviderCapability,
    ProviderRequestContext,
    create_provider_registry,
)
from creatoros.providers.cloudinary import (
    DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME,
    CloudinaryAssetHostingProvider,
    register_cloudinary_asset_hosting_provider,
)
from creatoros.providers.mock import MockAssetHostingProvider


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in synchronous unit tests."""

    return asyncio.run(coro)


def write_image(path: Path) -> Path:
    """Write a tiny deterministic image payload for hosting tests."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\nmock-png")
    return path


def build_asset(path: Path) -> GeneratedAsset:
    """Create one generated image asset that points to a local file path."""

    return GeneratedAsset(asset_type=AssetType.IMAGE, uri=str(path), metadata={"role": "scene_image"})


@dataclass
class FakeCloudinaryClient:
    """Simple fake Cloudinary client that records upload and delete calls."""

    upload_response: dict[str, object] = field(
        default_factory=lambda: {
            "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/creatoros/run_001/asset.png",
            "public_id": "creatoros/run_001/asset_123",
            "asset_id": "cloudinary_asset_123",
            "resource_type": "image",
            "format": "png",
            "width": 1024,
            "height": 1024,
        }
    )
    destroy_response: dict[str, object] = field(default_factory=lambda: {"result": "ok"})
    upload_error: Exception | None = None
    destroy_error: Exception | None = None
    upload_calls: list[dict[str, object]] = field(default_factory=list)
    destroy_calls: list[dict[str, object]] = field(default_factory=list)

    def upload(self, file: str, **kwargs: object) -> dict[str, object]:
        self.upload_calls.append({"file": file, **kwargs})
        if self.upload_error is not None:
            raise self.upload_error
        return dict(self.upload_response)

    def destroy(self, public_id: str, **kwargs: object) -> dict[str, object]:
        self.destroy_calls.append({"public_id": public_id, **kwargs})
        if self.destroy_error is not None:
            raise self.destroy_error
        return dict(self.destroy_response)


def build_provider(
    *,
    client: FakeCloudinaryClient | None = None,
    allowed_roots: tuple[Path, ...] | None = None,
    cloud_name: str | None = "demo-cloud",
    api_key: str | None = "cloudinary-key",
    api_secret: str | None = "cloudinary-secret",
    asset_folder: str = "creatoros",
) -> CloudinaryAssetHostingProvider:
    """Create a Cloudinary hosting provider with deterministic local test defaults."""

    return CloudinaryAssetHostingProvider(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        asset_folder=asset_folder,
        client=client,
        allowed_roots=allowed_roots,
    )


def test_cloudinary_provider_satisfies_runtime_protocol(tmp_path: Path) -> None:
    """The adapter should satisfy the provider-neutral hosting contract."""

    provider = build_provider(client=FakeCloudinaryClient(), allowed_roots=(tmp_path,))

    assert isinstance(provider, AssetHostingProvider)


def test_provider_info_exposes_hosting_identity_only() -> None:
    """Provider metadata should remain capability-focused and secret-free."""

    provider = build_provider(client=FakeCloudinaryClient(), allowed_roots=(Path.cwd(),))

    assert provider.info.name == DEFAULT_CLOUDINARY_ASSET_HOSTING_PROVIDER_NAME
    assert provider.info.provider_type == "hosting"
    assert provider.info.capabilities == {ProviderCapability.ASSET_HOSTING}
    assert "api_key" not in provider.info.metadata


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("cloud_name", {"cloud_name": None}),
        ("api_key", {"api_key": None}),
        ("api_secret", {"api_secret": None}),
    ],
)
def test_missing_required_configuration_is_rejected(
    field_name: str,
    kwargs: dict[str, object],
) -> None:
    """Missing Cloudinary credentials should fail locally at construction time."""

    with pytest.raises(CreatorOSValidationError) as exc_info:
        build_provider(**kwargs)

    assert exc_info.value.details["field"] == field_name


def test_host_uploads_local_image_with_safe_signed_configuration(tmp_path: Path) -> None:
    """Hosting should validate a local image path and forward safe Cloudinary options."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    client = FakeCloudinaryClient()
    provider = build_provider(client=client, allowed_roots=(tmp_path,))
    asset = build_asset(local_image)
    context = ProviderRequestContext(timeout_seconds=45.0, metadata={"run_id": "run 001"})
    before = asset.model_dump()

    result = run_async(provider.host(asset, context=context))

    assert asset.model_dump() == before
    assert result.data.public_url.startswith("https://")
    assert result.data.provider_asset_id == "creatoros/run_001/asset_123"
    assert result.data.request_id == "cloudinary_asset_123"
    assert result.data.metadata["resource_type"] == "image"
    assert client.upload_calls[0]["file"] == str(local_image)
    assert client.upload_calls[0]["public_id"].startswith("creatoros/run-001/")
    assert client.upload_calls[0]["overwrite"] is False
    assert client.upload_calls[0]["resource_type"] == "image"
    assert client.upload_calls[0]["timeout"] == 45.0


def test_host_rejects_non_image_assets(tmp_path: Path) -> None:
    """The Cloudinary adapter should currently support image hosting only."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    provider = build_provider(client=FakeCloudinaryClient(), allowed_roots=(tmp_path,))
    asset = GeneratedAsset(asset_type=AssetType.VIDEO, uri=str(local_image))

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(provider.host(asset))

    assert exc_info.value.details["field"] == "asset.asset_type"


def test_host_rejects_missing_empty_or_out_of_root_files(tmp_path: Path) -> None:
    """Local file validation should reject unsafe or unusable paths."""

    provider = build_provider(client=FakeCloudinaryClient(), allowed_roots=(tmp_path / "artifacts",))

    with pytest.raises(CreatorOSValidationError):
        run_async(provider.host(build_asset(tmp_path / "artifacts" / "run_001" / "images" / "missing.png")))

    empty_file = tmp_path / "artifacts" / "run_001" / "images" / "empty.png"
    empty_file.parent.mkdir(parents=True, exist_ok=True)
    empty_file.write_bytes(b"")
    with pytest.raises(CreatorOSValidationError):
        run_async(provider.host(build_asset(empty_file)))

    outside_file = write_image(tmp_path / "outside" / "scene.png")
    with pytest.raises(CreatorOSValidationError):
        run_async(provider.host(build_asset(outside_file)))


def test_host_rejects_non_https_or_malformed_cloudinary_responses(tmp_path: Path) -> None:
    """Malformed Cloudinary responses should fail normalization safely."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    provider = build_provider(
        client=FakeCloudinaryClient(
            upload_response={"secure_url": "http://example.com/image.png", "public_id": "creatoros/run_001/asset_123"}
        ),
        allowed_roots=(tmp_path,),
    )

    with pytest.raises(ProviderResponseError):
        run_async(provider.host(build_asset(local_image)))

    provider_missing_public_id = build_provider(
        client=FakeCloudinaryClient(upload_response={"secure_url": "https://example.com/image.png"}),
        allowed_roots=(tmp_path,),
    )
    with pytest.raises(ProviderResponseError):
        run_async(provider_missing_public_id.host(build_asset(local_image)))


def test_provider_errors_are_translated_safely_without_secret_leakage(tmp_path: Path) -> None:
    """Auth, rate-limit, and network failures should map to typed provider errors."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    asset = build_asset(local_image)

    auth_provider = build_provider(
        client=FakeCloudinaryClient(upload_error=RuntimeError("authentication failed for cloudinary-secret")),
        allowed_roots=(tmp_path,),
    )
    with pytest.raises(ProviderAuthenticationError) as auth_error:
        run_async(auth_provider.host(asset))
    assert "cloudinary-secret" not in str(auth_error.value)

    rate_provider = build_provider(
        client=FakeCloudinaryClient(upload_error=RuntimeError("rate limit exceeded")),
        allowed_roots=(tmp_path,),
    )
    with pytest.raises(ProviderRateLimitError):
        run_async(rate_provider.host(asset))

    network_provider = build_provider(
        client=FakeCloudinaryClient(upload_error=RuntimeError("network connection timeout")),
        allowed_roots=(tmp_path,),
    )
    with pytest.raises(ProviderUnavailableError):
        run_async(network_provider.host(asset))


def test_delete_calls_cloudinary_destroy_with_public_id(tmp_path: Path) -> None:
    """Delete should call the Cloudinary destroy path with the hosted public ID."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    client = FakeCloudinaryClient()
    provider = build_provider(client=client, allowed_roots=(tmp_path,))
    hosted_asset = run_async(provider.host(build_asset(local_image))).data

    result = run_async(provider.delete(hosted_asset))

    assert result.data is True
    assert client.destroy_calls[0]["public_id"] == hosted_asset.provider_asset_id
    assert client.destroy_calls[0]["resource_type"] == "image"


def test_delete_failure_is_translated_safely(tmp_path: Path) -> None:
    """Delete failures should surface typed provider errors without leaking secrets."""

    local_image = write_image(tmp_path / "artifacts" / "run_001" / "images" / "scene.png")
    client = FakeCloudinaryClient(destroy_error=RuntimeError("network delete failure"))
    provider = build_provider(client=client, allowed_roots=(tmp_path,))
    hosted_asset = run_async(provider.host(build_asset(local_image))).data

    with pytest.raises(ProviderUnavailableError):
        run_async(provider.delete(hosted_asset))


def test_registration_is_explicit_and_keeps_mock_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Explicit Cloudinary registration should work without replacing the mock default."""

    class StubSettings:
        cloudinary_cloud_name = "demo-cloud"
        cloudinary_api_key = "cloudinary-key"
        cloudinary_api_secret = "cloudinary-secret"
        cloudinary_asset_folder = "creatoros"
        default_asset_hosting_provider = "mock"

    registry = create_provider_registry()
    registry.register(MockAssetHostingProvider())
    monkeypatch.setattr("creatoros.providers.cloudinary.bootstrap.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    provider = register_cloudinary_asset_hosting_provider(
        registry,
        client=FakeCloudinaryClient(),
        allowed_roots=(tmp_path,),
    )

    assert provider is registry.get("hosting", "cloudinary")
    assert registry.get("hosting", "mock").info.name == "mock"


def test_registration_makes_zero_network_calls(tmp_path: Path) -> None:
    """Constructing and registering the provider should not upload or delete anything."""

    client = FakeCloudinaryClient()
    registry = create_provider_registry()

    provider = register_cloudinary_asset_hosting_provider(
        registry,
        cloud_name="demo-cloud",
        api_key="cloudinary-key",
        api_secret="cloudinary-secret",
        asset_folder="creatoros",
        client=client,
        allowed_roots=(tmp_path,),
    )

    assert provider.info.name == "cloudinary"
    assert client.upload_calls == []
    assert client.destroy_calls == []
