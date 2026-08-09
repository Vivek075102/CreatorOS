"""Unit tests for the concrete Kling HTTP transport."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.providers import create_provider_registry, resolve_default_video_provider
from creatoros.providers.kling import (
    DEFAULT_KLING_API_BASE_URL,
    DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH,
    DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL,
    DEFAULT_KLING_RESOLUTION_POLICY,
    DEFAULT_KLING_TASKS_ENDPOINT_PATH,
    KlingAuthenticationTransportError,
    KlingHTTPStatusTransportError,
    KlingHTTPVideoTransport,
    KlingMalformedResponseTransportError,
    KlingNetworkTransportError,
    KlingRateLimitTransportError,
    KlingTaskStatus,
    KlingVideoProvider,
    KlingVideoTaskRequest,
    register_kling_video_provider,
)
from creatoros.providers.mock import MockVideoProvider


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in synchronous unit tests."""

    return asyncio.run(coro)


def build_task_request(**overrides: object) -> KlingVideoTaskRequest:
    """Build one verified Kling image-to-video task request."""

    payload: dict[str, object] = {
        "prompt": "Add motion to this gaming scene",
        "model": DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL,
        "duration_seconds": 5.0,
        "width": 1080,
        "height": 1920,
        "reference_image_uri": "https://cdn.example.com/reference.png",
        "reference_image_is_local_path": False,
        "native_audio_enabled": False,
    }
    payload.update(overrides)
    return KlingVideoTaskRequest(**payload)


def build_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = DEFAULT_KLING_API_BASE_URL,
) -> KlingHTTPVideoTransport:
    """Build one offline Kling transport using an injected `httpx.MockTransport`."""

    http_client = httpx.AsyncClient(
        base_url=base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    return KlingHTTPVideoTransport(base_url=base_url, http_client=http_client)


def test_create_task_uses_verified_i2v_http_contract() -> None:
    """The verified Kling I2V submission should use the exact path, headers, and payload shape."""

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": {"id": "task_123", "status": "submitted"},
            },
            request=request,
        )

    transport = build_transport(handler)

    submission = run_async(
        transport.submit_video_task(
            build_task_request(),
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert submission.task_id == "task_123"
    assert captured["method"] == "POST"
    assert captured["path"] == DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH
    assert captured["authorization"] == "Bearer kling-secret"
    assert captured["content_type"] == "application/json"
    assert captured["json"] == {
        "contents": [
            {"type": "prompt", "text": "Add motion to this gaming scene"},
            {"type": "first_frame", "url": "https://cdn.example.com/reference.png"},
        ],
        "settings": {
            "resolution": DEFAULT_KLING_RESOLUTION_POLICY,
            "duration": 5,
        },
        "options": {
            "watermark_info": {
                "enabled": False,
            }
        },
    }


@pytest.mark.parametrize("duration_seconds", [2.0, 16.0])
def test_unsupported_duration_is_rejected_before_http(duration_seconds: float) -> None:
    """Unsupported Kling durations should fail before any HTTP request is attempted."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, request=request)

    transport = build_transport(handler)

    with pytest.raises(CreatorOSValidationError):
        run_async(
            transport.submit_video_task(
                build_task_request(duration_seconds=duration_seconds),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert call_count == 0


def test_fractional_duration_is_rejected_before_http() -> None:
    """Fractional Kling durations should fail before any HTTP request is attempted."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, request=request)

    transport = build_transport(handler)

    with pytest.raises(CreatorOSValidationError):
        run_async(
            transport.submit_video_task(
                build_task_request(duration_seconds=5.5),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert call_count == 0


def test_negative_prompt_is_rejected_before_http() -> None:
    """Unsupported negative prompts should fail explicitly rather than being invented."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, request=request)

    transport = build_transport(handler)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(
            transport.submit_video_task(
                build_task_request(negative_prompt="avoid text"),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert exc_info.value.details["field"] == "negative_prompt"
    assert call_count == 0


def test_local_reference_image_path_fails_preflight_before_http() -> None:
    """Local reference-image paths should fail preflight until provider-reachable URLs exist."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, request=request)

    transport = build_transport(handler)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(
            transport.submit_video_task(
                build_task_request(
                    reference_image_uri="C:/GamingAIFactory/artifacts/run_001/images/scene_001.png",
                    reference_image_is_local_path=True,
                ),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert "provider-reachable URL" in str(exc_info.value)
    assert call_count == 0


def test_text_to_video_transport_is_stopped_until_official_endpoint_is_verified() -> None:
    """Concrete live T2V should remain disabled until the official endpoint is verified."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, request=request)

    transport = build_transport(handler)

    with pytest.raises(Exception) as exc_info:
        run_async(
            transport.submit_video_task(
                build_task_request(reference_image_uri=None),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert "text-to-video endpoint is not yet verified" in str(exc_info.value).lower()
    assert call_count == 0


def test_malformed_create_response_is_rejected_safely() -> None:
    """Create-task responses without the expected task data should fail safely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "message": "success", "request_id": "req_123", "data": {}},
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.submit_video_task(
                build_task_request(),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_provider_error_code_is_rejected_safely() -> None:
    """Provider-side non-success codes should become safe normalized transport errors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 1001, "message": "rejected", "request_id": "req_123", "data": {}},
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingHTTPStatusTransportError) as exc_info:
        run_async(
            transport.submit_video_task(
                build_task_request(),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert "rejected" not in str(exc_info.value).lower()


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, KlingAuthenticationTransportError),
        (403, KlingAuthenticationTransportError),
        (429, KlingRateLimitTransportError),
    ],
)
def test_http_error_statuses_are_translated(
    status_code: int,
    expected_exception: type[Exception],
) -> None:
    """Verified HTTP error classes should map into the corresponding transport errors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    transport = build_transport(handler)

    with pytest.raises(expected_exception):
        run_async(
            transport.submit_video_task(
                build_task_request(),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_network_failure_is_translated_safely() -> None:
    """Network failures should become a safe Kling network transport error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    transport = build_transport(handler)

    with pytest.raises(KlingNetworkTransportError):
        run_async(
            transport.submit_video_task(
                build_task_request(),
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_create_task_is_issued_exactly_once_without_automatic_retries() -> None:
    """The transport must never automatically resubmit a paid create request."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": {"id": "task_123", "status": "submitted"},
            },
            request=request,
        )

    transport = build_transport(handler)

    submission = run_async(
        transport.submit_video_task(
            build_task_request(),
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert submission.task_id == "task_123"
    assert call_count == 1


@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [
        ("submitted", KlingTaskStatus.PENDING),
        ("processing", KlingTaskStatus.RUNNING),
        ("succeeded", KlingTaskStatus.SUCCEEDED),
        ("failed", KlingTaskStatus.FAILED),
    ],
)
def test_query_task_uses_verified_endpoint_and_status_mapping(
    provider_status: str,
    expected_status: KlingTaskStatus,
) -> None:
    """Query-task transport should use GET /tasks with task_ids and normalize the official statuses."""

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": provider_status,
                        "message": "provider internal message",
                        "outputs": [
                            {
                                "type": "video",
                                "id": "output_123",
                                "url": "https://example.invalid/generated.mp4?sig=secret",
                                "watermark_url": "https://example.invalid/generated-watermarked.mp4?sig=secret",
                                "duration": "5",
                            }
                        ],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    snapshot = run_async(
        transport.get_video_task(
            "task_123",
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert snapshot.task_id == "task_123"
    assert snapshot.status is expected_status
    assert captured["method"] == "GET"
    assert captured["path"] == DEFAULT_KLING_TASKS_ENDPOINT_PATH
    assert captured["query"] == {"task_ids": "task_123"}
    assert "external_task_ids" not in captured["query"]
    assert captured["authorization"] == "Bearer kling-secret"
    assert captured["content_type"] == "application/json"


def test_query_task_extracts_non_watermarked_video_output_and_normalizes_duration() -> None:
    """Succeeded query-task responses should use outputs[].url, ignore watermark_url, and parse duration."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": "succeeded",
                        "message": "provider internal message",
                        "outputs": [
                            {
                                "type": "image",
                                "id": "ignore_me",
                                "url": "https://example.invalid/ignore.png?sig=secret",
                            },
                            {
                                "type": "video",
                                "id": "output_123",
                                "url": "https://example.invalid/generated.mp4?sig=secret",
                                "watermark_url": "https://example.invalid/generated-watermarked.mp4?sig=secret",
                                "duration": "5.5",
                            },
                        ],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    snapshot = run_async(
        transport.get_video_task(
            "task_123",
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert snapshot.status is KlingTaskStatus.SUCCEEDED
    assert snapshot.output_url == "https://example.invalid/generated.mp4?sig=secret"
    assert snapshot.duration_seconds == 5.5
    assert "watermarked" not in (snapshot.output_url or "")


def test_query_task_failed_status_returns_safe_internal_failure_reason() -> None:
    """Failed task snapshots should normalize to a safe failure reason rather than raw provider text."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": "failed",
                        "message": "raw provider details that should not leak",
                        "outputs": [],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    snapshot = run_async(
        transport.get_video_task(
            "task_123",
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert snapshot.status is KlingTaskStatus.FAILED
    assert snapshot.failure_reason == "Kling task failed"


def test_query_task_unknown_status_is_rejected_safely() -> None:
    """Unknown official status values should fail safely rather than being guessed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [{"id": "task_123", "status": "mystery", "outputs": []}],
            },
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 0, "message": "success", "request_id": "req_123", "data": []},
        {"code": 0, "message": "success", "request_id": "req_123", "data": [{}]},
        {"code": 0, "message": "success", "request_id": "req_123", "data": [{"id": "task_123"}]},
    ],
)
def test_query_task_malformed_data_is_rejected_safely(payload: dict[str, object]) -> None:
    """Malformed query-task data structures should fail safely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_query_task_missing_outputs_is_rejected_safely() -> None:
    """Succeeded tasks without outputs should fail safely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [{"id": "task_123", "status": "succeeded"}],
            },
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_query_task_missing_video_output_is_rejected_safely() -> None:
    """Succeeded tasks without a video output entry should fail safely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": "succeeded",
                        "outputs": [{"type": "image", "url": "https://example.invalid/image.png?sig=secret"}],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_query_task_missing_video_url_is_rejected_safely() -> None:
    """Succeeded video outputs without a nonblank URL should fail safely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": "succeeded",
                        "outputs": [{"type": "video", "url": "   ", "duration": "5"}],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingMalformedResponseTransportError):
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )


def test_query_task_provider_error_code_is_rejected_safely() -> None:
    """Non-zero provider codes should fail safely without exposing provider details."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 1001, "message": "secret provider detail", "request_id": "req_123", "data": []},
            request=request,
        )

    transport = build_transport(handler)

    with pytest.raises(KlingHTTPStatusTransportError) as exc_info:
        run_async(
            transport.get_video_task(
                "task_123",
                authorization_header="Bearer kling-secret",
                timeout_seconds=90.0,
            )
        )

    assert "secret provider detail" not in str(exc_info.value)


def test_query_task_invalid_duration_string_leaves_duration_unset() -> None:
    """Invalid output duration strings should not invent a duration value."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "request_id": "req_123",
                "data": [
                    {
                        "id": "task_123",
                        "status": "succeeded",
                        "outputs": [{"type": "video", "url": "https://example.invalid/generated.mp4?sig=secret", "duration": "not-a-number"}],
                    }
                ],
            },
            request=request,
        )

    transport = build_transport(handler)

    snapshot = run_async(
        transport.get_video_task(
            "task_123",
            authorization_header="Bearer kling-secret",
            timeout_seconds=90.0,
        )
    )

    assert snapshot.duration_seconds is None


def test_download_returns_non_empty_bytes_without_file_writes() -> None:
    """Successful output downloads should return ephemeral video bytes only."""

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            content=b"binary-video",
            headers={"content-type": "video/mp4"},
            request=request,
        )

    transport = build_transport(handler, base_url="https://downloads.example.com")

    video = run_async(
        transport.download_video(
            "https://downloads.example.com/video/output.mp4?signature=secret",
            timeout_seconds=90.0,
        )
    )

    assert video.payload_bytes == b"binary-video"
    assert video.mime_type == "video/mp4"
    assert call_count == 1


def test_transport_construction_and_registration_make_zero_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concrete transport construction and provider registration should stay local-only."""

    class StubSettings:
        kling_api_key = "kling-secret"
        kling_api_base_url = DEFAULT_KLING_API_BASE_URL
        default_video_model = DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL
        default_video_provider = "mock"
        kling_video_timeout_seconds = 900.0
        kling_video_poll_interval_seconds = 5.0

    transport = KlingHTTPVideoTransport()
    registry = create_provider_registry()
    registry.register(MockVideoProvider())
    monkeypatch.setattr("creatoros.providers.kling.bootstrap.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    provider = register_kling_video_provider(registry)

    assert transport.base_url == DEFAULT_KLING_API_BASE_URL
    assert isinstance(provider, KlingVideoProvider)
    assert isinstance(provider._transport, KlingHTTPVideoTransport)
    assert provider._transport.base_url == DEFAULT_KLING_API_BASE_URL
    assert resolve_default_video_provider(registry).info.name == "mock"
