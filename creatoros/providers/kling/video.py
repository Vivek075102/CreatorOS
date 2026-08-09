"""Kling video provider shell for provider-neutral CreatorOS clip generation."""

from __future__ import annotations

import asyncio
import time
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import Field, field_validator

from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, CreatorOSModel, GeneratedAsset
from creatoros.observability import get_logger
from creatoros.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.media import GeneratedVideo, VideoGenerationRequest

DEFAULT_KLING_VIDEO_PROVIDER_NAME = "kling"
DEFAULT_KLING_VIDEO_MODEL: str | None = None
DEFAULT_KLING_VIDEO_TIMEOUT_SECONDS = 900.0
DEFAULT_KLING_VIDEO_POLL_INTERVAL_SECONDS = 5.0
_KLING_VIDEO_PROVIDER_TYPE = "video"
_DEFAULT_VIDEO_MIME_TYPE = "video/mp4"
_LOGGER = get_logger("providers.kling.video")


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional strings to stripped values or ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _monotonic() -> float:
    """Return a monotonic clock value behind a patchable local helper."""

    return time.monotonic()


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name, "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
        )
    return normalized_value


def _resolve_model(default_model: str | None) -> str:
    """Return the configured Kling video model or fail safely when missing."""

    normalized_model = _normalize_optional_string(default_model)
    if normalized_model is None:
        raise CreatorOSValidationError(
            "Kling video model is not configured",
            code="provider_invalid_input",
            details={
                "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
                "field": "default_video_model",
            },
        )
    return normalized_model


def _is_probably_remote_uri(uri: str) -> bool:
    """Return whether a reference-image URI looks like a remote reference."""

    lowered = uri.lower()
    return lowered.startswith(("http://", "https://")) or "://" in uri


class KlingTaskStatus(StrEnum):
    """Normalized internal Kling task states used by the provider shell."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class KlingVideoTaskRequest(CreatorOSModel):
    """Provider-owned normalized task request sent to an injected Kling transport."""

    prompt: str
    model: str
    duration_seconds: float
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = None
    negative_prompt: str | None = None
    reference_image_uri: str | None = None
    reference_image_is_local_path: bool = False
    native_audio_enabled: bool = False

    @field_validator("prompt", "model")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required values."""

        return _validate_non_blank(value, field_name=info.field_name)


class KlingTaskSubmission(CreatorOSModel):
    """Normalized submission acknowledgement returned by the injected transport."""

    task_id: str

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        """Require a non-blank provider task identifier."""

        return _validate_non_blank(value, field_name="task_id")


class KlingTaskSnapshot(CreatorOSModel):
    """Normalized task state returned by the injected transport."""

    task_id: str
    status: KlingTaskStatus
    output_url: str | None = None
    failure_reason: str | None = None
    duration_seconds: float | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = None
    mime_type: str = _DEFAULT_VIDEO_MIME_TYPE
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("task_id", "mime_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank task values."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("output_url", "failure_reason", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional text fields."""

        return _normalize_optional_string(value)


class KlingDownloadedVideo(CreatorOSModel):
    """Normalized downloaded video payload returned by the injected transport."""

    payload_bytes: bytes
    mime_type: str = _DEFAULT_VIDEO_MIME_TYPE

    @field_validator("payload_bytes")
    @classmethod
    def validate_payload_bytes(cls, value: bytes) -> bytes:
        """Require non-empty downloaded payload bytes."""

        if not value:
            raise ValueError("payload_bytes must not be empty")
        return bytes(value)

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        """Require a non-blank MIME type."""

        return _validate_non_blank(value, field_name="mime_type")


class KlingTransportError(Exception):
    """Base transport error for injected Kling client boundaries."""


class KlingAuthenticationTransportError(KlingTransportError):
    """Transport error for authentication failures."""


class KlingRateLimitTransportError(KlingTransportError):
    """Transport error for rate-limiting failures."""


class KlingNetworkTransportError(KlingTransportError):
    """Transport error for network availability failures."""


class KlingMalformedResponseTransportError(KlingTransportError):
    """Transport error for malformed provider responses."""


class _KlingVideoTransport(Protocol):
    """Injectable Kling transport boundary used for offline provider tests."""

    async def submit_video_task(
        self,
        request: KlingVideoTaskRequest,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSubmission:
        """Submit one Kling generation task."""

    async def get_video_task(
        self,
        task_id: str,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSnapshot:
        """Poll one previously submitted Kling generation task."""

    async def download_video(
        self,
        output_url: str,
        *,
        timeout_seconds: float,
    ) -> KlingDownloadedVideo:
        """Download one completed Kling video payload."""


class KlingVideoProvider:
    """Provider shell that encapsulates future Kling task polling behind VideoProvider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: _KlingVideoTransport | None = None,
        default_model: str | None = DEFAULT_KLING_VIDEO_MODEL,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
    ) -> None:
        self._info = ProviderInfo(
            name=DEFAULT_KLING_VIDEO_PROVIDER_NAME,
            provider_type=_KLING_VIDEO_PROVIDER_TYPE,
            capabilities={ProviderCapability.VIDEO_GENERATION},
            version="1.0",
            metadata={"api_style": "async_task"},
        )
        self._api_key = _normalize_optional_string(api_key)
        self._transport = transport
        self._default_model = _normalize_optional_string(default_model)
        self._timeout_seconds = (
            DEFAULT_KLING_VIDEO_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._poll_interval_seconds = (
            DEFAULT_KLING_VIDEO_POLL_INTERVAL_SECONDS
            if poll_interval_seconds is None
            else poll_interval_seconds
        )
        if self._timeout_seconds <= 0:
            raise CreatorOSValidationError(
                "timeout_seconds must be greater than zero",
                code="provider_invalid_input",
                details={"field": "timeout_seconds", "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
            )
        if self._poll_interval_seconds <= 0:
            raise CreatorOSValidationError(
                "poll_interval_seconds must be greater than zero",
                code="provider_invalid_input",
                details={"field": "poll_interval_seconds", "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
            )

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the Kling video adapter shell."""

        return self._info.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return local readiness only without network or task submission."""

        return (
            self._transport is not None
            and self._api_key is not None
            and self._default_model is not None
        )

    async def generate(
        self,
        request: VideoGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedVideo]:
        """Generate one video through the injected Kling async-task transport."""

        transport = self._get_transport()
        authorization_header = self._build_authorization_header()
        model = _resolve_model(self._default_model)
        timeout_seconds = (
            context.timeout_seconds
            if context is not None and context.timeout_seconds is not None
            else self._timeout_seconds
        )
        if timeout_seconds <= 0:
            raise CreatorOSValidationError(
                "timeout_seconds must be greater than zero",
                code="provider_invalid_input",
                details={"field": "timeout_seconds", "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
            )

        task_request = self._build_task_request(request=request, model=model)
        generation_mode = (
            "image_to_video" if request.reference_image is not None else "text_to_video"
        )
        _LOGGER.info(
            "provider_video_generation_started",
            provider_name=self.info.name,
            model=model,
            generation_mode=generation_mode,
        )

        try:
            submission = await transport.submit_video_task(
                task_request,
                authorization_header=authorization_header,
                timeout_seconds=timeout_seconds,
            )
            snapshot = await self._poll_until_terminal(
                transport=transport,
                task_id=submission.task_id,
                authorization_header=authorization_header,
                timeout_seconds=timeout_seconds,
            )
            if snapshot.status is not KlingTaskStatus.SUCCEEDED:
                raise ProviderResponseError(
                    "Kling video task failed",
                    code="provider_response_invalid",
                    details={
                        "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
                        "model": model,
                        "request_id": snapshot.task_id,
                    },
                )
            if snapshot.output_url is None:
                raise ProviderResponseError(
                    "Kling video task completed without a retrievable output",
                    code="provider_response_invalid",
                    details={
                        "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
                        "model": model,
                        "request_id": snapshot.task_id,
                    },
                )
            download = await transport.download_video(
                snapshot.output_url,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            translated_error = self._translate_error(error, model=model)
            _LOGGER.warning(
                "provider_video_generation_failed",
                provider_name=self.info.name,
                model=model,
                error_code=translated_error.code,
            )
            raise translated_error from error

        normalized_result = GeneratedVideo(
            artifact=GeneratedAsset(
                asset_type=AssetType.VIDEO,
                uri=f"{DEFAULT_KLING_VIDEO_PROVIDER_NAME}://generated/video/{submission.task_id}.mp4",
                metadata={"provider_reference_kind": "temporary"},
            ),
            provider_name=self.info.name,
            model=model,
            mime_type=download.mime_type,
            duration_seconds=(
                snapshot.duration_seconds
                if snapshot.duration_seconds is not None
                else request.duration_seconds
            ),
            width=snapshot.width if snapshot.width is not None else request.width,
            height=snapshot.height if snapshot.height is not None else request.height,
            fps=snapshot.fps if snapshot.fps is not None else request.fps,
            request_id=submission.task_id,
            metadata={
                "generation_mode": generation_mode,
                "native_audio_enabled": False,
                "reference_image_supplied": request.reference_image is not None,
            },
            payload_bytes=download.payload_bytes,
        )
        _LOGGER.info(
            "provider_video_generation_completed",
            provider_name=self.info.name,
            model=model,
            request_id=normalized_result.request_id,
            success=True,
        )
        return ProviderResult[GeneratedVideo](
            data=normalized_result,
            provider=self.info,
            usage=ProviderUsage(
                input_units=0,
                output_units=0,
                total_units=0,
                metadata={"task_polling": True},
            ),
            request_id=normalized_result.request_id,
            metadata={"generation_mode": generation_mode, "native_audio_enabled": False},
        )

    async def generate_video(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return the legacy compatibility video-asset contract."""

        request = VideoGenerationRequest(
            prompt=_validate_non_blank(prompt, field_name="prompt"),
            duration_seconds=3.0,
        )
        result = await self.generate(request, context=context)
        return ProviderResult[GeneratedAsset](
            data=result.data.artifact.model_copy(deep=True),
            provider=self.info,
            usage=result.usage.model_copy(deep=True) if result.usage is not None else None,
            request_id=result.request_id,
            metadata=dict(result.metadata),
        )

    def _build_authorization_header(self) -> str:
        """Construct the verified API-key Bearer authorization header."""

        if self._api_key is None:
            raise ProviderAuthenticationError(
                "Kling API key is not configured",
                code="provider_authentication_missing",
                details={"provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
                retryable=False,
            )
        return f"Bearer {self._api_key}"

    def _get_transport(self) -> _KlingVideoTransport:
        """Return the injected transport or fail safely when none is configured."""

        if self._transport is None:
            raise ProviderUnavailableError(
                "Kling transport is not configured",
                code="provider_unavailable",
                details={"provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME},
            )
        return self._transport

    def _build_task_request(
        self,
        *,
        request: VideoGenerationRequest,
        model: str,
    ) -> KlingVideoTaskRequest:
        """Translate one provider-neutral request into the provider-owned task contract."""

        reference_image_uri = None
        reference_image_is_local_path = False
        if request.reference_image is not None:
            reference_image_uri = request.reference_image.uri
            reference_image_is_local_path = not _is_probably_remote_uri(reference_image_uri)
            if reference_image_is_local_path:
                reference_path = Path(reference_image_uri)
                reference_image_uri = str(reference_path)

        return KlingVideoTaskRequest(
            prompt=request.prompt,
            model=model,
            duration_seconds=request.duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            negative_prompt=request.negative_prompt,
            reference_image_uri=reference_image_uri,
            reference_image_is_local_path=reference_image_is_local_path,
            native_audio_enabled=False,
        )

    async def _poll_until_terminal(
        self,
        *,
        transport: _KlingVideoTransport,
        task_id: str,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSnapshot:
        """Poll the same submitted task until a terminal state or timeout."""

        deadline = _monotonic() + timeout_seconds
        while True:
            snapshot = await transport.get_video_task(
                task_id,
                authorization_header=authorization_header,
                timeout_seconds=timeout_seconds,
            )
            if snapshot.status in {KlingTaskStatus.SUCCEEDED, KlingTaskStatus.FAILED}:
                return snapshot

            if snapshot.status not in {KlingTaskStatus.PENDING, KlingTaskStatus.RUNNING}:
                raise ProviderResponseError(
                    "Kling task returned an unknown status",
                    code="provider_response_invalid",
                    details={
                        "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
                        "request_id": task_id,
                    },
                )

            remaining_seconds = deadline - _monotonic()
            if remaining_seconds <= 0:
                raise ProviderTimeoutError(
                    "Kling video task polling timed out",
                    code="provider_timeout",
                    details={
                        "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
                        "request_id": task_id,
                    },
                )
            await asyncio.sleep(min(self._poll_interval_seconds, remaining_seconds))

    def _translate_error(
        self,
        error: Exception,
        *,
        model: str,
    ) -> (
        ProviderAuthenticationError
        | ProviderRateLimitError
        | ProviderTimeoutError
        | ProviderUnavailableError
        | ProviderResponseError
    ):
        """Translate transport failures into CreatorOS provider exceptions safely."""

        safe_details: dict[str, object] = {
            "provider_name": DEFAULT_KLING_VIDEO_PROVIDER_NAME,
            "model": model,
        }

        if isinstance(error, ProviderAuthenticationError | ProviderRateLimitError | ProviderTimeoutError | ProviderUnavailableError | ProviderResponseError):
            return error

        if isinstance(error, KlingAuthenticationTransportError):
            return ProviderAuthenticationError(
                "Kling video authentication failed",
                code="provider_authentication_failed",
                details=safe_details,
                retryable=False,
            )

        if isinstance(error, KlingRateLimitTransportError):
            return ProviderRateLimitError(
                "Kling video rate limit encountered",
                code="provider_rate_limited",
                details=safe_details,
            )

        if isinstance(error, KlingNetworkTransportError):
            return ProviderUnavailableError(
                "Kling video service is unavailable",
                code="provider_unavailable",
                details=safe_details,
            )

        if isinstance(error, KlingMalformedResponseTransportError):
            return ProviderResponseError(
                "Kling video response could not be normalized safely",
                code="provider_response_invalid",
                details=safe_details,
            )

        return ProviderResponseError(
            "Kling video request failed unexpectedly",
            code="provider_response_invalid",
            details=safe_details,
        )


__all__ = [
    "DEFAULT_KLING_VIDEO_MODEL",
    "DEFAULT_KLING_VIDEO_POLL_INTERVAL_SECONDS",
    "DEFAULT_KLING_VIDEO_PROVIDER_NAME",
    "DEFAULT_KLING_VIDEO_TIMEOUT_SECONDS",
    "KlingAuthenticationTransportError",
    "KlingDownloadedVideo",
    "KlingMalformedResponseTransportError",
    "KlingNetworkTransportError",
    "KlingRateLimitTransportError",
    "KlingTaskSnapshot",
    "KlingTaskStatus",
    "KlingTaskSubmission",
    "KlingTransportError",
    "KlingVideoProvider",
    "KlingVideoTaskRequest",
]
