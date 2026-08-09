"""Unit tests for the CreatorOS OpenAI image provider adapter."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from openai.types.image import Image
from openai.types.images_response import ImagesResponse, Usage

from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.providers import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageProvider,
    ProviderCapability,
    ProviderRequestContext,
    create_provider_registry,
    resolve_default_image_provider,
)
from creatoros.providers.mock import MockImageProvider
from creatoros.providers.openai import (
    DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
    OpenAIImageProvider,
    register_openai_image_provider,
)

MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def build_image_response(
    *,
    url: str | None = None,
    b64_json: str | None = None,
    output_format: str = "png",
    request_id: str = "req_img_123",
) -> ImagesResponse:
    """Create a minimal OpenAI SDK image response for deterministic tests."""

    if url is None and b64_json is None:
        b64_json = base64.b64encode(MINIMAL_PNG_BYTES).decode("ascii")

    response = ImagesResponse.model_construct(
        created=1234567890,
        background="auto",
        data=[
            Image.model_construct(
                url=url,
                b64_json=b64_json,
                revised_prompt="provider prompt rewrite should not escape",
            )
        ],
        output_format=output_format,
        quality="standard",
        size="1024x1024",
        usage=Usage.model_construct(
            input_tokens=12,
            input_tokens_details=None,
            output_tokens=34,
            total_tokens=46,
            output_tokens_details=None,
        ),
    )
    response._request_id = request_id
    return response


def build_binary_image_response() -> ImagesResponse:
    """Create a deterministic binary-backed OpenAI SDK image response."""

    return build_image_response(
        url=None,
        b64_json=base64.b64encode(MINIMAL_PNG_BYTES).decode("ascii"),
    )


@dataclass
class FakeImagesClient:
    """Simple async fake that records the most recent image request."""

    response: object | None = None
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def generate(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("response must be configured for this fake")
        return self.response


@dataclass
class FakeOpenAIImageClient:
    """Simple injected client exposing the OpenAI images interface."""

    images: FakeImagesClient


@dataclass
class FakeLogger:
    """Collect safe logging calls for assertions."""

    infos: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    warnings: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **kwargs: object) -> None:
        self.infos.append((event, dict(kwargs)))

    def warning(self, event: str, **kwargs: object) -> None:
        self.warnings.append((event, dict(kwargs)))


def build_provider(
    *,
    client: FakeOpenAIImageClient | None = None,
    api_key: str | None = None,
    default_model: str | None = "gpt-image-1",
) -> OpenAIImageProvider:
    """Create an image adapter with explicit local defaults for tests."""

    return OpenAIImageProvider(
        client=client,
        api_key=api_key,
        default_model=default_model,
        timeout_seconds=30.0,
        max_retries=0,
    )


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in unit tests without async plugins."""

    return asyncio.run(coro)


def test_openai_image_provider_satisfies_runtime_image_protocol() -> None:
    """The adapter should satisfy the runtime image-provider contract."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )

    assert isinstance(provider, ImageProvider)


def test_fake_client_construction_works_without_api_key() -> None:
    """Fake-client tests should not require a configured API key."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response())),
        api_key=None,
    )

    assert run_async(provider.health_check()) is True


def test_missing_api_key_fails_safely_when_real_client_is_needed() -> None:
    """Generating without an injected client or API key should fail safely."""

    provider = build_provider(client=None, api_key=None)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="render this")))

    assert exc_info.value.code == "provider_authentication_missing"
    assert exc_info.value.details == {"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME}


def test_provider_info_exposes_image_only_identity_without_api_key() -> None:
    """Provider metadata should identify the image capability only."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )

    assert provider.info.name == "openai-image"
    assert provider.info.provider_type == "image"
    assert provider.info.capabilities == {ProviderCapability.IMAGE_GENERATION}
    assert "api_key" not in provider.info.metadata


def test_generate_translates_request_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter should translate the request and normalize the image result."""

    fake_logger = FakeLogger()
    fake_images = FakeImagesClient(response=build_binary_image_response())
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))
    monkeypatch.setattr("creatoros.providers.openai.image._LOGGER", fake_logger)
    request = ImageGenerationRequest(prompt="Pixel art dragon", width=1024, height=1536)

    result = run_async(provider.generate(request))

    assert isinstance(result.data, GeneratedImage)
    assert result.provider.name == "openai-image"
    assert result.data.provider_name == "openai-image"
    assert result.data.model == "gpt-image-1"
    assert result.data.width == 1024
    assert result.data.height == 1536
    assert result.data.request_id == "req_img_123"
    assert result.data.mime_type == "image/png"
    assert result.data.artifact.uri.startswith("openai-image://generated/")
    assert result.data.artifact.metadata["provider_reference_kind"] == "temporary"
    assert result.data.metadata["transient_source"] == "binary"
    assert result.data.payload_bytes == MINIMAL_PNG_BYTES
    assert result.usage is not None
    assert result.usage.input_units == 12
    assert result.usage.output_units == 34
    assert result.usage.total_units == 46
    assert "https://example.invalid" not in str(result.model_dump())
    assert "b64_json" not in str(result.model_dump())
    assert len(fake_images.calls) == 1
    request_kwargs = fake_images.calls[0]
    assert request_kwargs["model"] == "gpt-image-1"
    assert request_kwargs["prompt"] == "Pixel art dragon"
    assert request_kwargs["size"] == "1024x1536"
    assert request_kwargs["timeout"] == 30.0
    assert "response_format" not in request_kwargs
    assert "output_format" not in request_kwargs
    assert set(request_kwargs) == {"model", "prompt", "size", "timeout"}
    assert all("prompt" not in payload for _, payload in fake_logger.infos)


def test_generate_uses_image_specific_default_timeout_when_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The image adapter should default to the dedicated image timeout setting."""

    class StubSettings:
        openai_image_timeout_seconds = 300.0

    fake_images = FakeImagesClient(response=build_image_response())
    monkeypatch.setattr("creatoros.providers.openai.image.get_settings", lambda: StubSettings())
    provider = OpenAIImageProvider(
        client=FakeOpenAIImageClient(fake_images),
        api_key="sk-test",
        default_model="gpt-image-1",
        max_retries=0,
    )

    run_async(provider.generate(ImageGenerationRequest(prompt="portrait")))

    assert fake_images.calls[0]["timeout"] == 300.0


def test_generate_uses_context_timeout_when_supplied() -> None:
    """Context timeout should override the image-specific provider timeout."""

    fake_images = FakeImagesClient(response=build_image_response())
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    run_async(
        provider.generate(
            ImageGenerationRequest(prompt="portrait"),
            context=ProviderRequestContext(timeout_seconds=90.0),
        )
    )
    assert fake_images.calls[0]["timeout"] == 90.0


def test_generate_never_sends_unsupported_response_format_argument() -> None:
    """The adapter should not send the known-bad response_format argument for GPT Image calls."""

    fake_images = FakeImagesClient(response=build_binary_image_response())
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    run_async(provider.generate(ImageGenerationRequest(prompt="compatibility check")))

    request_kwargs = fake_images.calls[0]
    assert "response_format" not in request_kwargs
    assert "output_format" not in request_kwargs


def test_generate_image_compatibility_returns_generated_asset() -> None:
    """The legacy compatibility method should still return only the artifact."""

    fake_images = FakeImagesClient(response=build_image_response())
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    result = run_async(provider.generate_image("Retro thumbnail"))

    assert result.data.asset_type.value == "image"
    assert result.data.uri.startswith("openai-image://generated/")


def test_unsupported_dimensions_are_rejected_safely() -> None:
    """Unsupported dimensions should fail clearly rather than rounding silently."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )
    request = ImageGenerationRequest(prompt="square", width=1000, height=1000)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(provider.generate(request))

    assert exc_info.value.details["field"] == "size"
    assert exc_info.value.details["width"] == 1000
    assert exc_info.value.details["height"] == 1000


def test_unsupported_optional_request_fields_are_rejected_explicitly() -> None:
    """Unsupported neutral fields should fail explicitly for this adapter."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )

    with pytest.raises(CreatorOSValidationError) as negative_prompt_error:
        run_async(
            provider.generate(
                ImageGenerationRequest(prompt="scene", negative_prompt="blurry")
            )
        )
    with pytest.raises(CreatorOSValidationError) as seed_error:
        run_async(provider.generate(ImageGenerationRequest(prompt="scene", seed=7)))

    assert negative_prompt_error.value.details["field"] == "negative_prompt"
    assert seed_error.value.details["field"] == "seed"


def test_request_object_is_not_mutated() -> None:
    """Generation should leave the caller's request model unchanged."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )
    request = ImageGenerationRequest(prompt="Forest temple", width=1024, height=1024)
    before = request.model_dump()

    run_async(provider.generate(request))

    assert request.model_dump() == before


def test_response_with_base64_only_is_normalized_without_storing_payload() -> None:
    """Base64-backed responses should normalize safely without retaining payload data."""

    response = build_image_response(url=None, b64_json=base64.b64encode(b"hello").decode("ascii"))
    provider = build_provider(client=FakeOpenAIImageClient(FakeImagesClient(response=response)))

    result = run_async(provider.generate(ImageGenerationRequest(prompt="sprite")))

    assert result.data.metadata["transient_source"] == "binary"
    assert result.data.payload_bytes == b"hello"
    assert base64.b64encode(b"hello").decode("ascii") not in str(result.model_dump())


def test_malformed_base64_payload_is_rejected_safely() -> None:
    """Malformed base64 image payloads should raise a typed provider response error."""

    response = build_image_response(url=None, b64_json="%%%not-base64%%%")
    provider = build_provider(client=FakeOpenAIImageClient(FakeImagesClient(response=response)))

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(ImageGenerationRequest(prompt="broken payload")))


def test_missing_image_output_is_rejected_safely() -> None:
    """Responses without image data should raise a typed provider response error."""

    empty_response = ImagesResponse.model_construct(
        created=1,
        background="auto",
        data=[],
        output_format="png",
        quality="standard",
        size="1024x1024",
        usage=None,
    )
    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=empty_response))
    )

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(ImageGenerationRequest(prompt="empty")))


def test_malformed_image_output_is_rejected_safely() -> None:
    """Responses with unusable image payloads should raise a typed error."""

    malformed_response = ImagesResponse.model_construct(
        created=1,
        background="auto",
        data=[
            Image.model_construct(
                url=None,
                b64_json=None,
                revised_prompt="provider prompt rewrite should not escape",
            )
        ],
        output_format="png",
        quality="standard",
        size="1024x1024",
        usage=None,
    )
    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=malformed_response))
    )

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(ImageGenerationRequest(prompt="broken")))


def test_auth_errors_are_translated_without_secret_leakage() -> None:
    """Authentication failures should map to typed auth errors safely."""

    request = httpx.Request("POST", "https://api.openai.com/v1/images")
    response = httpx.Response(401, request=request)
    fake_images = FakeImagesClient(
        error=openai.AuthenticationError(
            message="bad auth key sk-secret",
            response=response,
            body={"error": "bad"},
        )
    )
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="sensitive prompt")))

    assert exc_info.value.retryable is False
    assert "sk-secret" not in str(exc_info.value)
    assert "sensitive prompt" not in str(exc_info.value.details)


def test_rate_limit_errors_are_translated() -> None:
    """Rate-limit failures should map to the CreatorOS provider hierarchy."""

    request = httpx.Request("POST", "https://api.openai.com/v1/images")
    response = httpx.Response(429, request=request)
    fake_images = FakeImagesClient(
        error=openai.RateLimitError("rate limited", response=response, body=None)
    )
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    with pytest.raises(ProviderRateLimitError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="castle")))

    assert exc_info.value.retryable is True


def test_timeout_errors_are_translated() -> None:
    """Timeout failures should become normalized timeout errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/images")
    fake_images = FakeImagesClient(error=openai.APITimeoutError(request))
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    with pytest.raises(ProviderTimeoutError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="city")))

    assert exc_info.value.retryable is True
    assert exc_info.value.code == "provider_timeout"
    assert "city" not in str(exc_info.value.details)
    assert len(fake_images.calls) == 1


def test_openai_client_construction_uses_image_timeout_without_global_retry_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real client construction should use the dedicated image timeout and explicit retry count."""

    captured_kwargs: dict[str, object] = {}

    class StubSettings:
        openai_image_timeout_seconds = 300.0

    class StubAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)
            self.images = FakeImagesClient(response=build_image_response())

    monkeypatch.setattr("creatoros.providers.openai.image.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.openai.image.AsyncOpenAI", StubAsyncOpenAI)

    provider = OpenAIImageProvider(
        client=None,
        api_key="sk-test",
        default_model="gpt-image-1",
        max_retries=0,
    )

    client = provider._get_client()

    assert isinstance(client.images, FakeImagesClient)
    assert captured_kwargs["api_key"] == "sk-test"
    assert captured_kwargs["timeout"] == 300.0
    assert captured_kwargs["max_retries"] == 0


def test_connection_errors_are_translated() -> None:
    """Connection failures should become provider unavailable errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/images")
    fake_images = FakeImagesClient(
        error=openai.APIConnectionError(message="no route", request=request)
    )
    provider = build_provider(client=FakeOpenAIImageClient(fake_images))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="island")))

    assert exc_info.value.retryable is True


def test_unexpected_failures_are_translated_safely() -> None:
    """Unexpected failures should become safe normalized provider errors."""

    provider = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(error=RuntimeError("prompt + payload")))
    )

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.generate(ImageGenerationRequest(prompt="do not leak me")))

    assert "do not leak me" not in str(exc_info.value.details)
    assert exc_info.value.code == "provider_response_invalid"


def test_health_check_is_local_and_requires_model_and_credentials_or_client() -> None:
    """Health should remain a local readiness check with zero network calls."""

    ready_with_client = build_provider(
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response()))
    )
    ready_with_api_key = build_provider(client=None, api_key="sk-test")
    missing_model = build_provider(client=None, api_key="sk-test", default_model=None)

    assert run_async(ready_with_client.health_check()) is True
    assert run_async(ready_with_api_key.health_check()) is True
    assert run_async(missing_model.health_check()) is False


def test_register_openai_image_provider_registers_explicitly_without_changing_mock_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit image registration should work while mock remains the configured default."""

    class StubSettings:
        openai_api_key = "sk-test"
        default_image_model = "gpt-image-1"
        default_image_provider = "mock"
        openai_image_timeout_seconds = 300.0
        provider_timeout_seconds = 30.0
        provider_max_retries = 3

    registry = create_provider_registry()
    registry.register(MockImageProvider())
    monkeypatch.setattr("creatoros.providers.openai.bootstrap.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    provider = register_openai_image_provider(
        registry,
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response())),
    )

    assert provider is registry.get("image", "openai-image")
    assert registry.contains("image", "openai-image")
    assert resolve_default_image_provider(registry).info.name == "mock"
    assert provider._timeout_seconds == 300.0
    assert provider._max_retries == 0


def test_registered_image_provider_uses_image_specific_timeout_not_generic_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should preserve the slower dedicated image timeout policy."""

    class StubSettings:
        openai_api_key = "sk-test"
        default_image_model = "gpt-image-1"
        default_image_provider = "mock"
        openai_image_timeout_seconds = 300.0
        provider_timeout_seconds = 30.0
        provider_max_retries = 3

    registry = create_provider_registry()
    monkeypatch.setattr("creatoros.providers.openai.bootstrap.get_settings", lambda: StubSettings())

    provider = register_openai_image_provider(
        registry,
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response())),
    )

    assert provider._timeout_seconds == StubSettings.openai_image_timeout_seconds
    assert provider._timeout_seconds != StubSettings.provider_timeout_seconds
    assert provider._max_retries == 0


def test_direct_and_registered_image_providers_share_the_same_safe_timeout_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap registration should match direct provider construction for image timeout safety."""

    class StubSettings:
        openai_api_key = "sk-test"
        default_image_model = "gpt-image-1"
        default_image_provider = "mock"
        openai_image_timeout_seconds = 300.0
        provider_timeout_seconds = 30.0
        provider_max_retries = 3

    monkeypatch.setattr("creatoros.providers.openai.image.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.openai.bootstrap.get_settings", lambda: StubSettings())

    direct_provider = OpenAIImageProvider(api_key="sk-test", default_model="gpt-image-1")
    registry = create_provider_registry()
    registered_provider = register_openai_image_provider(
        registry,
        client=FakeOpenAIImageClient(FakeImagesClient(response=build_image_response())),
    )

    assert direct_provider._timeout_seconds == registered_provider._timeout_seconds == 300.0
    assert direct_provider._max_retries == registered_provider._max_retries == 0


def test_openai_image_module_contains_no_file_or_pipeline_side_effects() -> None:
    """The adapter module should stay focused on provider translation only."""

    module_source = Path("creatoros/providers/openai/image.py").read_text(encoding="utf-8")

    assert "GamingMediaAgent" not in module_source
    assert "GamingContentPipeline" not in module_source
    assert "Cloudinary" not in module_source
    assert "ffmpeg" not in module_source.lower()
    assert "open(" not in module_source
