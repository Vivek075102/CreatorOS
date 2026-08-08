"""OpenAI image provider adapter for CreatorOS."""

from __future__ import annotations

import base64
import hashlib
from typing import Protocol, cast

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from creatoros.config import get_settings
from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.observability import get_logger
from creatoros.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.media import GeneratedImage, ImageGenerationRequest

DEFAULT_OPENAI_IMAGE_PROVIDER_NAME = "openai-image"
DEFAULT_OPENAI_IMAGE_MODEL: str | None = None
_OPENAI_IMAGE_PROVIDER_TYPE = "image"
_REQUESTED_OUTPUT_FORMAT = "png"
_REQUESTED_RESPONSE_FORMAT = "b64_json"
_SUPPORTED_IMAGE_SIZES: dict[tuple[int, int], str] = {
    (256, 256): "256x256",
    (512, 512): "512x512",
    (1024, 1024): "1024x1024",
    (1536, 1024): "1536x1024",
    (1024, 1536): "1024x1536",
    (1792, 1024): "1792x1024",
    (1024, 1792): "1024x1792",
}
_MIME_TYPES_BY_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
_LOGGER = get_logger("providers.openai.image")


class _ImagesClient(Protocol):
    """Minimal async images client contract used by the adapter."""

    async def generate(self, **kwargs: object) -> object:
        """Create one image-generation response."""


class _AsyncOpenAIImageClient(Protocol):
    """Minimal async OpenAI client contract used by the adapter."""

    @property
    def images(self) -> _ImagesClient:
        """Return the images API client."""


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name, "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
        )
    return normalized_value


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional strings to stripped values or ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _safe_request_id(response: object) -> str | None:
    """Return a request identifier when the SDK exposes one."""

    request_id = getattr(response, "_request_id", None)
    if isinstance(request_id, str):
        normalized_request_id = request_id.strip()
        if normalized_request_id:
            return normalized_request_id
    return None


def _safe_response_created(response: object) -> int | None:
    """Return the created timestamp when present on the SDK response."""

    created = getattr(response, "created", None)
    if isinstance(created, int):
        return created
    return None


def _size_to_openai_value(width: int, height: int) -> str:
    """Translate exact provider-neutral dimensions into supported OpenAI size values."""

    size = _SUPPORTED_IMAGE_SIZES.get((width, height))
    if size is None:
        raise CreatorOSValidationError(
            "requested image dimensions are not supported by the OpenAI image adapter",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
                "field": "size",
                "width": width,
                "height": height,
                "supported_sizes": sorted(_SUPPORTED_IMAGE_SIZES.values()),
            },
        )
    return size


def _resolve_model(default_model: str | None) -> str:
    """Return the configured image model or fail safely when it is missing."""

    normalized_model = _normalize_optional_string(default_model)
    if normalized_model is None:
        raise CreatorOSValidationError(
            "OpenAI image model is not configured",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
                "field": "default_model",
            },
        )
    return normalized_model


def _normalize_usage(response: object) -> ProviderUsage | None:
    """Convert SDK usage metadata into CreatorOS usage metadata."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if not isinstance(input_tokens, int | None):
        input_tokens = None
    if not isinstance(output_tokens, int | None):
        output_tokens = None
    if not isinstance(total_tokens, int | None):
        total_tokens = None

    return ProviderUsage(
        input_units=input_tokens,
        output_units=output_tokens,
        total_units=total_tokens,
    )


def _normalize_output_format(response: object) -> str:
    """Return the output format used by the response or adapter request."""

    output_format = getattr(response, "output_format", None)
    if isinstance(output_format, str):
        normalized_output_format = output_format.strip().lower()
        if normalized_output_format in _MIME_TYPES_BY_FORMAT:
            return normalized_output_format
    return _REQUESTED_OUTPUT_FORMAT


def _build_artifact_uri(
    *,
    request_id: str | None,
    created: int | None,
    image_index: int,
    url: str | None,
    b64_json: str | None,
) -> str:
    """Return one safe provider-owned artifact reference without storing raw payloads."""

    digest_source = request_id or ""
    if created is not None:
        digest_source = f"{digest_source}|{created}"
    if url is not None:
        digest_source = f"{digest_source}|url|{url}"
    if b64_json is not None:
        digest_source = f"{digest_source}|b64|{b64_json}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:24]
    return f"{DEFAULT_OPENAI_IMAGE_PROVIDER_NAME}://generated/{digest}/{image_index}"


def _decode_b64_payload(b64_json: str) -> bytes:
    """Decode provider image base64 safely into binary payload bytes."""

    try:
        decoded_bytes = base64.b64decode(b64_json, validate=True)
    except Exception as error:
        raise ProviderResponseError(
            "OpenAI image response contained invalid base64 payload data",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
        ) from error

    if not decoded_bytes:
        raise ProviderResponseError(
            "OpenAI image response contained an empty image payload",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
        )
    return decoded_bytes


def _normalize_image_result(
    response: object,
    *,
    request: ImageGenerationRequest,
    model: str,
) -> GeneratedImage:
    """Convert one OpenAI image response into the provider-neutral image contract."""

    data = getattr(response, "data", None)
    if not isinstance(data, list) or not data:
        raise ProviderResponseError(
            "OpenAI image response did not contain any generated images",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME, "model": model},
        )

    first_image = data[0]
    url = getattr(first_image, "url", None)
    b64_json = getattr(first_image, "b64_json", None)
    if not isinstance(url, str):
        url = None
    if not isinstance(b64_json, str):
        b64_json = None
    if url is None and b64_json is None:
        raise ProviderResponseError(
            "OpenAI image response did not contain a usable image reference",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME, "model": model},
        )

    request_id = _safe_request_id(response)
    created = _safe_response_created(response)
    output_format = _normalize_output_format(response)
    payload_bytes = None if b64_json is None else _decode_b64_payload(b64_json)
    artifact = GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri=_build_artifact_uri(
            request_id=request_id,
            created=created,
            image_index=0,
            url=url,
            b64_json=b64_json,
        ),
        metadata={
            "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
            "provider_reference_kind": "temporary",
            "transient_source": "url" if payload_bytes is None else "binary",
        },
    )
    metadata: dict[str, object] = {
        "provider_reference_kind": "temporary",
        "transient_source": "url" if payload_bytes is None else "binary",
    }
    if created is not None:
        metadata["response_created"] = created

    return GeneratedImage(
        artifact=artifact,
        provider_name=DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
        model=model,
        mime_type=_MIME_TYPES_BY_FORMAT[output_format],
        width=request.width,
        height=request.height,
        request_id=request_id,
        metadata=metadata,
        payload_bytes=payload_bytes,
    )


class OpenAIImageProvider:
    """Provider adapter that normalizes OpenAI image generation for CreatorOS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: _AsyncOpenAIImageClient | None = None,
        default_model: str | None = DEFAULT_OPENAI_IMAGE_MODEL,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._info = ProviderInfo(
            name=DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
            provider_type=_OPENAI_IMAGE_PROVIDER_TYPE,
            capabilities={ProviderCapability.IMAGE_GENERATION},
            version="1.0",
            metadata={"api_style": "images.generate"},
        )
        self._default_model = _normalize_optional_string(default_model)
        self._timeout_seconds = (
            get_settings().provider_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        self._max_retries = 0 if max_retries is None else max_retries
        if self._timeout_seconds <= 0:
            raise CreatorOSValidationError(
                "timeout_seconds must be greater than zero",
                code="provider_invalid_input",
                details={"field": "timeout_seconds", "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
            )
        if self._max_retries < 0:
            raise CreatorOSValidationError(
                "max_retries must be zero or greater",
                code="provider_invalid_input",
                details={"field": "max_retries", "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
            )

        normalized_api_key = _normalize_optional_string(api_key)
        self._api_key = normalized_api_key
        self._client: _AsyncOpenAIImageClient | None = client

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the OpenAI image adapter."""

        return self._info.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return local readiness without making a live network request."""

        return (self._client is not None or self._api_key is not None) and self._default_model is not None

    async def generate(
        self,
        request: ImageGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedImage]:
        """Execute one normalized OpenAI image request and return a typed image result."""

        if request.negative_prompt is not None:
            raise CreatorOSValidationError(
                "negative_prompt is not supported by the OpenAI image adapter",
                code="provider_invalid_input",
                details={
                    "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
                    "field": "negative_prompt",
                },
            )
        if request.seed is not None:
            raise CreatorOSValidationError(
                "seed is not supported by the OpenAI image adapter",
                code="provider_invalid_input",
                details={
                    "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
                    "field": "seed",
                },
            )

        client = self._get_client()
        model = _resolve_model(self._default_model)
        size = _size_to_openai_value(request.width, request.height)
        timeout_seconds = request_context_timeout = None
        if context is not None:
            request_context_timeout = context.timeout_seconds
        timeout_seconds = request_context_timeout if request_context_timeout is not None else self._timeout_seconds

        request_kwargs: dict[str, object] = {
            "model": model,
            "prompt": request.prompt,
            "size": size,
            "output_format": _REQUESTED_OUTPUT_FORMAT,
            "response_format": _REQUESTED_RESPONSE_FORMAT,
            "timeout": timeout_seconds,
        }

        _LOGGER.info(
            "provider_image_generation_started",
            provider_name=self.info.name,
            model=model,
            width=request.width,
            height=request.height,
        )

        try:
            raw_response = await client.images.generate(**request_kwargs)
        except Exception as error:
            translated_error = self._translate_error(error, model=model)
            _LOGGER.warning(
                "provider_image_generation_failed",
                provider_name=self.info.name,
                model=model,
                width=request.width,
                height=request.height,
                error_code=translated_error.code,
            )
            raise translated_error from error

        normalized_result = _normalize_image_result(raw_response, request=request, model=model)
        _LOGGER.info(
            "provider_image_generation_completed",
            provider_name=self.info.name,
            model=normalized_result.model,
            width=normalized_result.width,
            height=normalized_result.height,
            request_id=normalized_result.request_id,
            success=True,
        )
        return ProviderResult[GeneratedImage](
            data=normalized_result,
            provider=self.info,
            usage=_normalize_usage(raw_response),
            request_id=normalized_result.request_id,
            metadata={
                "size": size,
                "output_format": _normalize_output_format(raw_response),
            },
        )

    async def generate_image(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return the legacy compatibility image asset contract."""

        request = ImageGenerationRequest(prompt=_validate_non_blank(prompt, field_name="prompt"))
        result = await self.generate(request, context=context)
        return ProviderResult[GeneratedAsset](
            data=result.data.artifact.model_copy(deep=True),
            provider=self.info,
            usage=result.usage.model_copy(deep=True) if result.usage is not None else None,
            request_id=result.request_id,
            metadata=dict(result.metadata),
        )

    def _get_client(self) -> _AsyncOpenAIImageClient:
        """Return the injected client or create one from safe configuration."""

        if self._client is not None:
            return self._client

        if self._api_key is None:
            raise ProviderAuthenticationError(
                "OpenAI API key is not configured",
                code="provider_authentication_missing",
                details={"provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME},
                retryable=False,
            )

        self._client = cast(
            _AsyncOpenAIImageClient,
            AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
            ),
        )
        return self._client

    def _translate_error(self, error: Exception, *, model: str) -> ProviderResponseError | ProviderAuthenticationError | ProviderRateLimitError | ProviderTimeoutError | ProviderUnavailableError:
        """Translate vendor SDK failures into typed CreatorOS provider exceptions."""

        safe_details: dict[str, object] = {
            "provider_name": DEFAULT_OPENAI_IMAGE_PROVIDER_NAME,
            "model": model,
        }

        if isinstance(error, AuthenticationError):
            return ProviderAuthenticationError(
                "OpenAI image authentication failed",
                code="provider_authentication_failed",
                details=safe_details,
                retryable=False,
            )

        if isinstance(error, RateLimitError):
            return ProviderRateLimitError(
                "OpenAI image rate limit encountered",
                code="provider_rate_limited",
                details=safe_details,
            )

        if isinstance(error, APITimeoutError | TimeoutError | httpx.TimeoutException):
            return ProviderTimeoutError(
                "OpenAI image request timed out",
                code="provider_timeout",
                details=safe_details,
            )

        if isinstance(error, APIConnectionError | httpx.NetworkError):
            return ProviderUnavailableError(
                "OpenAI image service is unavailable",
                code="provider_unavailable",
                details=safe_details,
            )

        if isinstance(error, APIStatusError):
            status_code = getattr(error, "status_code", None)
            if isinstance(status_code, int):
                safe_details["status_code"] = status_code

            request_id = _safe_request_id(error.response)
            if request_id is not None:
                safe_details["request_id"] = request_id

            if status_code in {401, 403}:
                return ProviderAuthenticationError(
                    "OpenAI image authentication failed",
                    code="provider_authentication_failed",
                    details=safe_details,
                    retryable=False,
                )

            if status_code == 429:
                return ProviderRateLimitError(
                    "OpenAI image rate limit encountered",
                    code="provider_rate_limited",
                    details=safe_details,
                )

            if isinstance(status_code, int) and status_code >= 500:
                return ProviderUnavailableError(
                    "OpenAI image service is unavailable",
                    code="provider_unavailable",
                    details=safe_details,
                )

            return ProviderResponseError(
                "OpenAI image response could not be normalized safely",
                code="provider_response_invalid",
                details=safe_details,
            )

        return ProviderResponseError(
            "OpenAI image request failed unexpectedly",
            code="provider_response_invalid",
            details=safe_details,
        )


__all__ = [
    "DEFAULT_OPENAI_IMAGE_MODEL",
    "DEFAULT_OPENAI_IMAGE_PROVIDER_NAME",
    "OpenAIImageProvider",
]
