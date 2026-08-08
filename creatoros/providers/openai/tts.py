"""OpenAI TTS provider adapter for CreatorOS."""

from __future__ import annotations

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
)
from creatoros.providers.media import GeneratedAudio, TTSGenerationRequest

DEFAULT_OPENAI_TTS_PROVIDER_NAME = "openai-tts"
DEFAULT_OPENAI_TTS_MODEL: str | None = None
_OPENAI_TTS_PROVIDER_TYPE = "voice"
_REQUESTED_RESPONSE_FORMAT = "mp3"
_SUPPORTED_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/L16",
}
_SUPPORTED_VOICES = frozenset(
    {
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "fable",
        "nova",
        "onyx",
        "sage",
        "shimmer",
        "verse",
    }
)
_LOGGER = get_logger("providers.openai.tts")


class _SpeechClient(Protocol):
    """Minimal async speech client contract used by the adapter."""

    async def create(self, **kwargs: object) -> object:
        """Create one speech-generation response."""


class _AudioClient(Protocol):
    """Minimal async audio client contract used by the adapter."""

    @property
    def speech(self) -> _SpeechClient:
        """Return the audio speech API client."""


class _AsyncOpenAITTSClient(Protocol):
    """Minimal async OpenAI client contract used by the adapter."""

    @property
    def audio(self) -> _AudioClient:
        """Return the audio API client."""


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional strings to stripped values or ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _resolve_model(default_model: str | None) -> str:
    """Return the configured TTS model or fail safely when it is missing."""

    normalized_model = _normalize_optional_string(default_model)
    if normalized_model is None:
        raise CreatorOSValidationError(
            "OpenAI TTS model is not configured",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
                "field": "default_tts_model",
            },
        )
    return normalized_model


def _resolve_voice(request: TTSGenerationRequest) -> str:
    """Return the requested voice or fail safely when it is missing or unsupported."""

    voice = _normalize_optional_string(request.voice)
    if voice is None:
        raise CreatorOSValidationError(
            "voice is required for the OpenAI TTS adapter",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
                "field": "voice",
            },
        )

    normalized_voice = voice.lower()
    if normalized_voice not in _SUPPORTED_VOICES:
        raise CreatorOSValidationError(
            "voice is not supported by the OpenAI TTS adapter",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
                "field": "voice",
                "supported_voices": sorted(_SUPPORTED_VOICES),
            },
        )
    return normalized_voice


def _validate_supported_request_fields(request: TTSGenerationRequest) -> None:
    """Reject unsupported provider-neutral fields for this adapter explicitly."""

    if request.language is not None:
        raise CreatorOSValidationError(
            "language is not supported by the OpenAI TTS adapter",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
                "field": "language",
            },
        )


def _safe_request_id(response: object) -> str | None:
    """Return a request identifier when the SDK response exposes one."""

    request_id = getattr(response, "_request_id", None)
    if isinstance(request_id, str):
        normalized_request_id = request_id.strip()
        if normalized_request_id:
            return normalized_request_id

    http_response = getattr(response, "response", None)
    if isinstance(http_response, httpx.Response):
        header_request_id = http_response.headers.get("x-request-id")
        if isinstance(header_request_id, str):
            normalized_request_id = header_request_id.strip()
            if normalized_request_id:
                return normalized_request_id
    return None


def _safe_http_response(response: object) -> httpx.Response:
    """Return the underlying HTTP response or fail safely when it is unavailable."""

    http_response = getattr(response, "response", None)
    if not isinstance(http_response, httpx.Response):
        raise ProviderResponseError(
            "OpenAI TTS response did not expose a readable HTTP response",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
        )
    return http_response


async def _read_audio_bytes(response: object) -> bytes:
    """Read audio bytes from the OpenAI binary wrapper safely."""

    reader = getattr(response, "aread", None)
    if callable(reader):
        audio_bytes = await reader()
    else:
        content = getattr(response, "content", None)
        if not isinstance(content, bytes):
            raise ProviderResponseError(
                "OpenAI TTS response did not contain readable audio bytes",
                code="provider_response_invalid",
                details={"provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
            )
        audio_bytes = content

    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise ProviderResponseError(
            "OpenAI TTS response did not contain any audio output",
            code="provider_response_invalid",
            details={"provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
        )
    return audio_bytes


def _normalize_mime_type(http_response: httpx.Response) -> str:
    """Return a normalized mime type for the configured response format."""

    content_type = http_response.headers.get("content-type")
    if content_type is not None:
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        if normalized_content_type:
            return normalized_content_type
    return _SUPPORTED_MIME_TYPES[_REQUESTED_RESPONSE_FORMAT]


def _build_artifact_uri(
    *,
    request_id: str | None,
    audio_bytes: bytes,
) -> str:
    """Return one safe provider-owned artifact reference without storing audio bytes."""

    digest = hashlib.sha256(audio_bytes).hexdigest()[:24]
    request_segment = "requestless" if request_id is None else request_id
    return f"{DEFAULT_OPENAI_TTS_PROVIDER_NAME}://generated/{request_segment}/{digest}.{_REQUESTED_RESPONSE_FORMAT}"


def _normalize_audio_result(
    *,
    request: TTSGenerationRequest,
    model: str,
    voice: str,
    request_id: str | None,
    mime_type: str,
    audio_bytes: bytes,
) -> GeneratedAudio:
    """Normalize one OpenAI speech result into the provider-neutral audio contract."""

    artifact = GeneratedAsset(
        asset_type=AssetType.AUDIO,
        uri=_build_artifact_uri(request_id=request_id, audio_bytes=audio_bytes),
        metadata={
            "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
            "provider_reference_kind": "temporary",
            "transient_source": "binary",
        },
    )
    return GeneratedAudio(
        artifact=artifact,
        provider_name=DEFAULT_OPENAI_TTS_PROVIDER_NAME,
        model=model,
        mime_type=mime_type,
        voice=voice,
        language=request.language,
        estimated_duration_seconds=None,
        request_id=request_id,
        metadata={
            "provider_reference_kind": "temporary",
            "transient_source": "binary",
            "duration_provided": False,
        },
        payload_bytes=audio_bytes,
    )


class OpenAITTSProvider:
    """Provider adapter that normalizes OpenAI speech generation for CreatorOS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: _AsyncOpenAITTSClient | None = None,
        default_model: str | None = DEFAULT_OPENAI_TTS_MODEL,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._info = ProviderInfo(
            name=DEFAULT_OPENAI_TTS_PROVIDER_NAME,
            provider_type=_OPENAI_TTS_PROVIDER_TYPE,
            capabilities={ProviderCapability.VOICE_GENERATION},
            version="1.0",
            metadata={"api_style": "audio.speech.create"},
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
                details={"field": "timeout_seconds", "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
            )
        if self._max_retries < 0:
            raise CreatorOSValidationError(
                "max_retries must be zero or greater",
                code="provider_invalid_input",
                details={"field": "max_retries", "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
            )

        self._api_key = _normalize_optional_string(api_key)
        self._client: _AsyncOpenAITTSClient | None = client

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the OpenAI TTS adapter."""

        return self._info.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return local readiness without making a live network request."""

        return (self._client is not None or self._api_key is not None) and self._default_model is not None

    async def generate(
        self,
        request: TTSGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAudio]:
        """Execute one normalized OpenAI TTS request and return a typed audio result."""

        _validate_supported_request_fields(request)
        client = self._get_client()
        model = _resolve_model(self._default_model)
        voice = _resolve_voice(request)
        timeout_seconds = context.timeout_seconds if context is not None and context.timeout_seconds is not None else self._timeout_seconds

        request_kwargs: dict[str, object] = {
            "input": request.text,
            "model": model,
            "voice": voice,
            "response_format": _REQUESTED_RESPONSE_FORMAT,
            "timeout": timeout_seconds,
        }
        if request.speed is not None:
            request_kwargs["speed"] = request.speed

        _LOGGER.info(
            "provider_tts_generation_started",
            provider_name=self.info.name,
            model=model,
            voice=voice,
        )

        try:
            raw_response = await client.audio.speech.create(**request_kwargs)
        except Exception as error:
            translated_error = self._translate_error(error, model=model, voice=voice)
            _LOGGER.warning(
                "provider_tts_generation_failed",
                provider_name=self.info.name,
                model=model,
                voice=voice,
                error_code=translated_error.code,
            )
            raise translated_error from error

        http_response = _safe_http_response(raw_response)
        audio_bytes = await _read_audio_bytes(raw_response)
        request_id = _safe_request_id(raw_response)
        normalized_result = _normalize_audio_result(
            request=request,
            model=model,
            voice=voice,
            request_id=request_id,
            mime_type=_normalize_mime_type(http_response),
            audio_bytes=audio_bytes,
        )
        _LOGGER.info(
            "provider_tts_generation_completed",
            provider_name=self.info.name,
            model=normalized_result.model,
            voice=voice,
            request_id=normalized_result.request_id,
            success=True,
        )
        return ProviderResult[GeneratedAudio](
            data=normalized_result,
            provider=self.info,
            usage=None,
            request_id=normalized_result.request_id,
            metadata={"response_format": _REQUESTED_RESPONSE_FORMAT},
        )

    def _get_client(self) -> _AsyncOpenAITTSClient:
        """Return the injected client or create one from safe configuration."""

        if self._client is not None:
            return self._client

        if self._api_key is None:
            raise ProviderAuthenticationError(
                "OpenAI API key is not configured",
                code="provider_authentication_missing",
                details={"provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME},
                retryable=False,
            )

        self._client = cast(
            _AsyncOpenAITTSClient,
            AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
            ),
        )
        return self._client

    def _translate_error(
        self,
        error: Exception,
        *,
        model: str,
        voice: str,
    ) -> ProviderAuthenticationError | ProviderRateLimitError | ProviderTimeoutError | ProviderUnavailableError | ProviderResponseError:
        """Translate vendor SDK failures into typed CreatorOS provider exceptions."""

        safe_details: dict[str, object] = {
            "provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME,
            "model": model,
            "voice": voice,
        }

        if isinstance(error, AuthenticationError):
            return ProviderAuthenticationError(
                "OpenAI TTS authentication failed",
                code="provider_authentication_failed",
                details=safe_details,
                retryable=False,
            )

        if isinstance(error, RateLimitError):
            return ProviderRateLimitError(
                "OpenAI TTS rate limit encountered",
                code="provider_rate_limited",
                details=safe_details,
            )

        if isinstance(error, APITimeoutError | TimeoutError | httpx.TimeoutException):
            return ProviderTimeoutError(
                "OpenAI TTS request timed out",
                code="provider_timeout",
                details=safe_details,
            )

        if isinstance(error, APIConnectionError | httpx.NetworkError):
            return ProviderUnavailableError(
                "OpenAI TTS service is unavailable",
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
                    "OpenAI TTS authentication failed",
                    code="provider_authentication_failed",
                    details=safe_details,
                    retryable=False,
                )

            if status_code == 429:
                return ProviderRateLimitError(
                    "OpenAI TTS rate limit encountered",
                    code="provider_rate_limited",
                    details=safe_details,
                )

            if isinstance(status_code, int) and status_code >= 500:
                return ProviderUnavailableError(
                    "OpenAI TTS service is unavailable",
                    code="provider_unavailable",
                    details=safe_details,
                )

            return ProviderResponseError(
                "OpenAI TTS response could not be normalized safely",
                code="provider_response_invalid",
                details=safe_details,
            )

        return ProviderResponseError(
            "OpenAI TTS request failed unexpectedly",
            code="provider_response_invalid",
            details=safe_details,
        )


__all__ = [
    "DEFAULT_OPENAI_TTS_MODEL",
    "DEFAULT_OPENAI_TTS_PROVIDER_NAME",
    "OpenAITTSProvider",
]
