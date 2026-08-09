"""Concrete offline-testable HTTP transport for the verified Kling video API surface."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from creatoros.core import CreatorOSValidationError
from creatoros.observability import get_logger
from creatoros.providers.kling.video import (
    KlingAuthenticationTransportError,
    KlingDownloadedVideo,
    KlingMalformedResponseTransportError,
    KlingNetworkTransportError,
    KlingRateLimitTransportError,
    KlingTaskSnapshot,
    KlingTaskStatus,
    KlingTaskSubmission,
    KlingTransportError,
    KlingVideoTaskRequest,
)

DEFAULT_KLING_API_BASE_URL = "https://api-singapore.klingai.com"
DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL = "kling-3.0-turbo"
DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH = "/image-to-video/kling-3.0-turbo"
DEFAULT_KLING_TASKS_ENDPOINT_PATH = "/tasks"
DEFAULT_KLING_RESOLUTION_POLICY = "1080p"
_SUPPORTED_DURATIONS = frozenset(range(3, 16))
_JSON_CONTENT_TYPE = "application/json"
_VERIFIED_SUCCESS_CODE = 0
_LOGGER = get_logger("providers.kling.transport")


class KlingHTTPStatusTransportError(KlingTransportError):
    """Transport error for safe normalized HTTP or provider-status failures."""


_STATUS_MAP = {
    "submitted": KlingTaskStatus.PENDING,
    "processing": KlingTaskStatus.RUNNING,
    "succeeded": KlingTaskStatus.SUCCEEDED,
    "failed": KlingTaskStatus.FAILED,
}


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional text values to stripped strings or ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _normalize_base_url(base_url: str) -> str:
    """Normalize and validate the configured Kling API base URL."""

    normalized_base_url = base_url.strip()
    if not normalized_base_url:
        raise CreatorOSValidationError(
            "kling_api_base_url must not be blank",
            code="provider_invalid_input",
            details={"field": "kling_api_base_url", "provider_name": "kling"},
        )
    return normalized_base_url.rstrip("/")


def _safe_json_mapping(response: httpx.Response) -> Mapping[str, object]:
    """Return one JSON mapping response or fail safely when malformed."""

    try:
        payload = response.json()
    except Exception as error:
        raise KlingMalformedResponseTransportError(
            "Kling response body was not valid JSON",
        ) from error

    if not isinstance(payload, Mapping):
        raise KlingMalformedResponseTransportError(
            "Kling response body was not a JSON object",
        )
    return payload


def _safe_nested_mapping(
    mapping: Mapping[str, object],
    key: str,
    *,
    error_message: str,
) -> Mapping[str, object]:
    """Return one nested mapping or fail safely when it is missing."""

    nested_value = mapping.get(key)
    if not isinstance(nested_value, Mapping):
        raise KlingMalformedResponseTransportError(error_message)
    return nested_value


def _safe_mapping_list(
    mapping: Mapping[str, object],
    key: str,
    *,
    error_message: str,
) -> list[Mapping[str, object]]:
    """Return one list of mappings or fail safely when malformed."""

    nested_value = mapping.get(key)
    if not isinstance(nested_value, list):
        raise KlingMalformedResponseTransportError(error_message)

    items: list[Mapping[str, object]] = []
    for item in nested_value:
        if not isinstance(item, Mapping):
            raise KlingMalformedResponseTransportError(error_message)
        items.append(item)
    return items


def _safe_duration_seconds(value: object) -> float | None:
    """Return a normalized output duration when Kling supplies a valid string or number."""

    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value:
            return None
        try:
            return float(normalized_value)
        except ValueError:
            return None
    return None


def _normalized_status(value: object) -> KlingTaskStatus:
    """Normalize one officially verified Kling task status value."""

    if not isinstance(value, str):
        raise KlingMalformedResponseTransportError(
            "Kling task status was missing or invalid",
        )

    normalized_value = value.strip().lower()
    try:
        return _STATUS_MAP[normalized_value]
    except KeyError as error:
        raise KlingMalformedResponseTransportError(
            "Kling task status was not recognized",
        ) from error


def _extract_video_output(task_data: Mapping[str, object]) -> tuple[str, float | None]:
    """Return the first non-watermarked video URL and optional duration from a succeeded task."""

    outputs = _safe_mapping_list(
        task_data,
        "outputs",
        error_message="Kling task outputs were missing or invalid",
    )
    for output in outputs:
        output_type = output.get("type")
        if not isinstance(output_type, str) or output_type.strip().lower() != "video":
            continue

        output_url = output.get("url")
        if not isinstance(output_url, str) or not output_url.strip():
            raise KlingMalformedResponseTransportError(
                "Kling video output URL was missing",
            )
        return output_url.strip(), _safe_duration_seconds(output.get("duration"))

    raise KlingMalformedResponseTransportError(
        "Kling task did not include a video output",
    )


def _map_http_error(response: httpx.Response) -> KlingTransportError:
    """Translate one non-success HTTP response into a safe transport error."""

    status_code = response.status_code
    if status_code in {401, 403}:
        return KlingAuthenticationTransportError("Kling authentication failed")
    if status_code == 429:
        return KlingRateLimitTransportError("Kling rate limit encountered")
    return KlingHTTPStatusTransportError(
        f"Kling request failed with HTTP {status_code}",
    )


def _validated_duration_seconds(duration_seconds: float) -> int:
    """Validate that Kling duration is an exact supported integer number of seconds."""

    if not float(duration_seconds).is_integer():
        raise CreatorOSValidationError(
            "Kling duration must be an exact integer number of seconds",
            code="provider_invalid_input",
            details={
                "field": "duration_seconds",
                "provider_name": "kling",
                "supported_durations": sorted(_SUPPORTED_DURATIONS),
            },
        )

    duration_value = int(duration_seconds)
    if duration_value not in _SUPPORTED_DURATIONS:
        raise CreatorOSValidationError(
            "Kling duration must be between 3 and 15 seconds inclusive",
            code="provider_invalid_input",
            details={
                "field": "duration_seconds",
                "provider_name": "kling",
                "supported_durations": sorted(_SUPPORTED_DURATIONS),
            },
        )
    return duration_value


def _build_create_payload(request: KlingVideoTaskRequest) -> dict[str, object]:
    """Build the verified Kling image-to-video create-task request body."""

    if request.negative_prompt is not None:
        raise CreatorOSValidationError(
            "negative_prompt is not supported by the current verified Kling image-to-video API contract",
            code="provider_invalid_input",
            details={"field": "negative_prompt", "provider_name": "kling"},
        )
    if request.reference_image_uri is None:
        raise KlingTransportError(
            "Text-to-video transport is not enabled because the official Kling text-to-video endpoint is not yet verified",
        )
    if request.reference_image_is_local_path:
        raise CreatorOSValidationError(
            "Reference image requires a provider-reachable URL for the current verified Kling image-to-video API",
            code="provider_invalid_input",
            details={"field": "reference_image", "provider_name": "kling"},
        )
    if request.model != DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL:
        raise CreatorOSValidationError(
            "Kling model is not supported by the current verified image-to-video transport",
            code="provider_invalid_input",
            details={
                "field": "model",
                "provider_name": "kling",
                "supported_models": [DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL],
            },
        )

    duration_value = _validated_duration_seconds(request.duration_seconds)
    return {
        "contents": [
            {
                "type": "prompt",
                "text": request.prompt,
            },
            {
                "type": "first_frame",
                "url": request.reference_image_uri,
            },
        ],
        "settings": {
            "resolution": DEFAULT_KLING_RESOLUTION_POLICY,
            "duration": duration_value,
        },
        "options": {
            "watermark_info": {
                "enabled": False,
            }
        },
    }


class KlingHTTPVideoTransport:
    """Concrete `httpx` transport for the verified Kling image-to-video task API."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_KLING_API_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._owns_client = http_client is None
        self._client = (
            httpx.AsyncClient(
                base_url=self._base_url,
                follow_redirects=False,
            )
            if http_client is None
            else http_client
        )

    @property
    def base_url(self) -> str:
        """Return the configured Kling API base URL."""

        return self._base_url

    async def aclose(self) -> None:
        """Close the owned HTTP client when the transport created it."""

        if self._owns_client:
            await self._client.aclose()

    async def submit_video_task(
        self,
        request: KlingVideoTaskRequest,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSubmission:
        """Submit one verified Kling image-to-video create-task request."""

        payload = _build_create_payload(request)
        response = await self._send_json_request(
            method="POST",
            path=DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH,
            authorization_header=authorization_header,
            timeout_seconds=timeout_seconds,
            json_payload=payload,
        )
        response_payload = _safe_json_mapping(response)

        provider_code = response_payload.get("code")
        if provider_code != _VERIFIED_SUCCESS_CODE:
            raise KlingHTTPStatusTransportError(
                "Kling create-task response indicated a provider-side failure",
            )

        data = _safe_nested_mapping(
            response_payload,
            "data",
            error_message="Kling create-task response did not contain a valid data object",
        )
        task_id = data.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise KlingMalformedResponseTransportError(
                "Kling create-task response did not contain a valid task identifier",
            )

        return KlingTaskSubmission(task_id=task_id)

    async def get_video_task(
        self,
        task_id: str,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSnapshot:
        """Query one verified Kling task by task ID and normalize its current state safely."""

        response = await self._send_request(
            method="GET",
            path=DEFAULT_KLING_TASKS_ENDPOINT_PATH,
            authorization_header=authorization_header,
            timeout_seconds=timeout_seconds,
            params={"task_ids": task_id},
        )
        response_payload = _safe_json_mapping(response)

        provider_code = response_payload.get("code")
        if provider_code != _VERIFIED_SUCCESS_CODE:
            raise KlingHTTPStatusTransportError(
                "Kling query-task response indicated a provider-side failure",
            )

        data = response_payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
            raise KlingMalformedResponseTransportError(
                "Kling query-task response did not contain exactly one valid task record",
            )

        task_data = data[0]
        returned_task_id = task_data.get("id")
        if not isinstance(returned_task_id, str) or not returned_task_id.strip():
            raise KlingMalformedResponseTransportError(
                "Kling query-task response did not contain a valid task identifier",
            )

        status = _normalized_status(task_data.get("status"))
        output_url: str | None = None
        duration_seconds: float | None = None
        failure_reason: str | None = None

        if status is KlingTaskStatus.SUCCEEDED:
            output_url, duration_seconds = _extract_video_output(task_data)
        elif status is KlingTaskStatus.FAILED:
            failure_reason = "Kling task failed"

        return KlingTaskSnapshot(
            task_id=returned_task_id,
            status=status,
            output_url=output_url,
            failure_reason=failure_reason,
            duration_seconds=duration_seconds,
        )

    async def download_video(
        self,
        output_url: str,
        *,
        timeout_seconds: float,
    ) -> KlingDownloadedVideo:
        """Download one completed Kling output URL into ephemeral payload bytes."""

        normalized_output_url = _normalize_optional_string(output_url)
        if normalized_output_url is None:
            raise KlingMalformedResponseTransportError(
                "Kling output URL was missing",
            )

        try:
            response = await self._client.get(
                normalized_output_url,
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
            )
        except httpx.TimeoutException as error:
            raise KlingNetworkTransportError("Kling video download timed out") from error
        except httpx.NetworkError as error:
            raise KlingNetworkTransportError("Kling video download failed") from error

        if response.status_code >= 400:
            raise _map_http_error(response)

        payload_bytes = response.content
        if not payload_bytes:
            raise KlingMalformedResponseTransportError(
                "Kling video download response was empty",
            )

        content_type = response.headers.get("content-type")
        mime_type = "video/mp4"
        if isinstance(content_type, str):
            normalized_content_type = content_type.split(";", 1)[0].strip().lower()
            if normalized_content_type:
                mime_type = normalized_content_type

        _LOGGER.info(
            "provider_video_download_completed",
            provider_name="kling",
            mime_type=mime_type,
            byte_count=len(payload_bytes),
        )
        return KlingDownloadedVideo(payload_bytes=payload_bytes, mime_type=mime_type)

    async def _send_json_request(
        self,
        *,
        method: str,
        path: str,
        authorization_header: str,
        timeout_seconds: float,
        json_payload: Mapping[str, object],
    ) -> httpx.Response:
        """Send one JSON request without retries and translate transport failures safely."""

        return await self._send_request(
            method=method,
            path=path,
            authorization_header=authorization_header,
            timeout_seconds=timeout_seconds,
            json_payload=json_payload,
        )

    async def _send_request(
        self,
        *,
        method: str,
        path: str,
        authorization_header: str,
        timeout_seconds: float,
        json_payload: Mapping[str, object] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Send one HTTP request without retries and translate transport failures safely."""

        try:
            response = await self._client.request(
                method,
                path,
                headers={
                    "Authorization": authorization_header,
                    "Content-Type": _JSON_CONTENT_TYPE,
                },
                json=None if json_payload is None else dict(json_payload),
                params=None if params is None else dict(params),
                timeout=httpx.Timeout(timeout_seconds),
            )
        except httpx.TimeoutException as error:
            raise KlingNetworkTransportError("Kling request timed out") from error
        except httpx.NetworkError as error:
            raise KlingNetworkTransportError("Kling request failed") from error

        if response.status_code >= 400:
            raise _map_http_error(response)
        return response


__all__ = [
    "DEFAULT_KLING_API_BASE_URL",
    "DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH",
    "DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL",
    "DEFAULT_KLING_RESOLUTION_POLICY",
    "DEFAULT_KLING_TASKS_ENDPOINT_PATH",
    "KlingHTTPStatusTransportError",
    "KlingHTTPVideoTransport",
]
