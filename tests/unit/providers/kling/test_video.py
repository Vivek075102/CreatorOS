"""Unit tests for the CreatorOS Kling video provider shell."""

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
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    GeneratedVideo,
    ProviderCapability,
    ProviderRequestContext,
    VideoGenerationRequest,
    VideoProvider,
    create_provider_registry,
    resolve_default_video_provider,
)
from creatoros.providers.kling import (
    KlingAuthenticationTransportError,
    KlingDownloadedVideo,
    KlingMalformedResponseTransportError,
    KlingNetworkTransportError,
    KlingRateLimitTransportError,
    KlingTaskSnapshot,
    KlingTaskStatus,
    KlingTaskSubmission,
    KlingVideoProvider,
    register_kling_video_provider,
)
from creatoros.providers.mock import MockVideoProvider


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in synchronous unit tests."""

    return asyncio.run(coro)


def build_reference_image(
    uri: str = "mock://generated/image/reference.png",
) -> GeneratedAsset:
    """Create one provider-neutral reference image asset."""

    return GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri=uri,
        metadata={"source": "test"},
    )


@dataclass
class FakeKlingTransport:
    """Injectable fake transport used to test the Kling provider shell offline."""

    submit_response: KlingTaskSubmission = field(
        default_factory=lambda: KlingTaskSubmission(task_id="task_123")
    )
    snapshots: list[object] = field(
        default_factory=lambda: [
            KlingTaskSnapshot(
                task_id="task_123",
                status=KlingTaskStatus.SUCCEEDED,
                output_url="https://example.invalid/generated.mp4?sig=secret",
                duration_seconds=5.0,
                width=1080,
                height=1920,
                fps=30.0,
            )
        ]
    )
    download_response: KlingDownloadedVideo = field(
        default_factory=lambda: KlingDownloadedVideo(payload_bytes=b"fake-video-bytes")
    )
    submit_error: Exception | None = None
    poll_error: Exception | None = None
    download_error: Exception | None = None
    submit_calls: list[dict[str, object]] = field(default_factory=list)
    poll_calls: list[dict[str, object]] = field(default_factory=list)
    download_calls: list[dict[str, object]] = field(default_factory=list)

    async def submit_video_task(
        self,
        request,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> KlingTaskSubmission:
        self.submit_calls.append(
            {
                "request": request,
                "authorization_header": authorization_header,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.submit_error is not None:
            raise self.submit_error
        return self.submit_response

    async def get_video_task(
        self,
        task_id: str,
        *,
        authorization_header: str,
        timeout_seconds: float,
    ) -> object:
        self.poll_calls.append(
            {
                "task_id": task_id,
                "authorization_header": authorization_header,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.poll_error is not None:
            raise self.poll_error
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    async def download_video(
        self,
        output_url: str,
        *,
        timeout_seconds: float,
    ) -> KlingDownloadedVideo:
        self.download_calls.append(
            {
                "output_url": output_url,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.download_error is not None:
            raise self.download_error
        return self.download_response


def build_provider(
    *,
    transport: FakeKlingTransport | None = None,
    api_key: str | None = "kling-test-key",
    default_model: str | None = "kling-video-model",
    timeout_seconds: float = 900.0,
    poll_interval_seconds: float = 0.01,
) -> KlingVideoProvider:
    """Create one Kling provider shell for offline tests."""

    return KlingVideoProvider(
        transport=transport,
        api_key=api_key,
        default_model=default_model,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def test_provider_satisfies_runtime_video_protocol() -> None:
    """The Kling adapter should satisfy the runtime video-provider contract."""

    provider = build_provider(transport=FakeKlingTransport())

    assert isinstance(provider, VideoProvider)


def test_provider_identity_and_capability_are_correct_without_secret_leakage() -> None:
    """Provider info should expose only safe Kling identity metadata."""

    provider = build_provider(transport=FakeKlingTransport())

    assert provider.info.name == "kling"
    assert provider.info.provider_type == "video"
    assert provider.info.capabilities == {ProviderCapability.VIDEO_GENERATION}
    assert "api_key" not in str(provider.info.metadata).lower()


def test_construction_makes_zero_network_calls() -> None:
    """Constructing the provider shell should not call the injected transport."""

    transport = FakeKlingTransport()
    build_provider(transport=transport)

    assert transport.submit_calls == []
    assert transport.poll_calls == []
    assert transport.download_calls == []


def test_health_check_is_local_only() -> None:
    """Health should depend on local config and injected transport only."""

    ready = build_provider(transport=FakeKlingTransport())
    missing_transport = build_provider(transport=None)
    missing_model = build_provider(transport=FakeKlingTransport(), default_model=None)

    assert run_async(ready.health_check()) is True
    assert run_async(missing_transport.health_check()) is False
    assert run_async(missing_model.health_check()) is False


def test_missing_credential_fails_safely() -> None:
    """Generating without a Kling API key should fail safely."""

    provider = build_provider(transport=FakeKlingTransport(), api_key=None)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(VideoGenerationRequest(prompt="shot", duration_seconds=5.0)))

    assert exc_info.value.code == "provider_authentication_missing"


def test_missing_model_fails_safely() -> None:
    """Generating without a configured Kling model should fail safely."""

    provider = build_provider(transport=FakeKlingTransport(), default_model=None)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(provider.generate(VideoGenerationRequest(prompt="shot", duration_seconds=5.0)))

    assert exc_info.value.details["field"] == "default_video_model"


def test_invalid_timeout_and_poll_interval_are_rejected() -> None:
    """Provider-specific timeout settings must remain positive."""

    with pytest.raises(CreatorOSValidationError):
        build_provider(transport=FakeKlingTransport(), timeout_seconds=0.0)

    with pytest.raises(CreatorOSValidationError):
        build_provider(transport=FakeKlingTransport(), poll_interval_seconds=0.0)


def test_text_to_video_request_maps_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text-to-video requests should map cleanly into the internal task request."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport()
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    result = run_async(
        provider.generate(
            VideoGenerationRequest(
                prompt="Vertical action clip",
                duration_seconds=5.0,
                width=1080,
                height=1920,
                fps=30.0,
            )
        )
    )

    submit_request = transport.submit_calls[0]["request"]
    assert submit_request.prompt == "Vertical action clip"
    assert submit_request.duration_seconds == 5.0
    assert submit_request.width == 1080
    assert submit_request.height == 1920
    assert submit_request.fps == 30.0
    assert submit_request.reference_image_uri is None
    assert submit_request.native_audio_enabled is False
    assert result.data.metadata["generation_mode"] == "text_to_video"


def test_context_timeout_overrides_provider_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit context timeout should override the provider-specific Kling timeout."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport()
    provider = build_provider(transport=transport, timeout_seconds=900.0)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    run_async(
        provider.generate(
            VideoGenerationRequest(prompt="clip", duration_seconds=5.0),
            context=ProviderRequestContext(timeout_seconds=120.0),
        )
    )

    assert transport.submit_calls[0]["timeout_seconds"] == 120.0
    assert transport.poll_calls[0]["timeout_seconds"] == 120.0
    assert transport.download_calls[0]["timeout_seconds"] == 120.0


def test_image_to_video_reference_is_forwarded_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reference-image requests should preserve provider-neutral asset identity safely."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    reference_image = build_reference_image()
    transport = FakeKlingTransport()
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)
    request = VideoGenerationRequest(
        prompt="Add motion to this still",
        duration_seconds=5.0,
        reference_image=reference_image,
    )
    before = reference_image.model_dump(mode="json")

    result = run_async(provider.generate(request))

    submit_request = transport.submit_calls[0]["request"]
    assert submit_request.reference_image_uri == "mock://generated/image/reference.png"
    assert submit_request.reference_image_is_local_path is False
    assert reference_image.model_dump(mode="json") == before
    assert result.data.metadata["reference_image_supplied"] is True
    assert "payload_bytes" not in str(result.data.metadata)


def test_local_reference_image_path_is_detected_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local materialized reference-image paths should remain local path references."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    local_path = str(Path("C:/GamingAIFactory/artifacts/run_001/images/scene_001.png"))
    transport = FakeKlingTransport()
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    run_async(
        provider.generate(
            VideoGenerationRequest(
                prompt="Animate the local frame",
                duration_seconds=5.0,
                reference_image=build_reference_image(local_path),
            )
        )
    )

    submit_request = transport.submit_calls[0]["request"]
    assert submit_request.reference_image_uri == local_path
    assert submit_request.reference_image_is_local_path is True


def test_native_audio_is_explicitly_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kling generation should remain visuals-only for CreatorOS."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport()
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    result = run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))

    assert transport.submit_calls[0]["request"].native_audio_enabled is False
    assert result.data.metadata["native_audio_enabled"] is False


def test_task_is_submitted_once_and_pending_state_polls_same_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling should reuse the same submitted task rather than resubmitting."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport(
        snapshots=[
            KlingTaskSnapshot(task_id="task_123", status=KlingTaskStatus.PENDING),
            KlingTaskSnapshot(task_id="task_123", status=KlingTaskStatus.RUNNING),
            KlingTaskSnapshot(
                task_id="task_123",
                status=KlingTaskStatus.SUCCEEDED,
                output_url="https://example.invalid/generated.mp4?sig=secret",
            ),
        ]
    )
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))

    assert len(transport.submit_calls) == 1
    assert [call["task_id"] for call in transport.poll_calls] == ["task_123", "task_123", "task_123"]


def test_failed_task_raises_safe_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed provider task should become a safe normalized provider error."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport(
        snapshots=[
            KlingTaskSnapshot(
                task_id="task_123",
                status=KlingTaskStatus.FAILED,
                failure_reason="hidden internal failure",
            )
        ]
    )
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.generate(VideoGenerationRequest(prompt="do not leak", duration_seconds=5.0)))

    assert exc_info.value.code == "provider_response_invalid"
    assert "do not leak" not in str(exc_info.value)


def test_unknown_status_is_rejected_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown task states should fail safely rather than being guessed."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    class UnknownSnapshot:
        task_id = "task_123"
        status = "mystery"
        output_url = None

    transport = FakeKlingTransport(snapshots=[UnknownSnapshot()])
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))

    assert exc_info.value.code == "provider_response_invalid"


def test_polling_is_bounded_and_timeout_does_not_resubmit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout should stop polling without resubmitting a second paid task."""

    transport = FakeKlingTransport(
        snapshots=[KlingTaskSnapshot(task_id="task_123", status=KlingTaskStatus.PENDING)]
    )
    provider = build_provider(transport=transport, timeout_seconds=1.0, poll_interval_seconds=0.5)
    monotonic_values = iter([0.0, 2.0])
    monkeypatch.setattr("creatoros.providers.kling.video._monotonic", lambda: next(monotonic_values))

    with pytest.raises(ProviderTimeoutError):
        run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))

    assert len(transport.submit_calls) == 1
    assert len(transport.poll_calls) == 1


def test_success_state_returns_normalized_generated_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful task completion should normalize into GeneratedVideo."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport(
        snapshots=[
            KlingTaskSnapshot(
                task_id="task_123",
                status=KlingTaskStatus.SUCCEEDED,
                output_url="https://example.invalid/generated.mp4?sig=secret",
                duration_seconds=5.0,
                width=1080,
                height=1920,
                fps=30.0,
            )
        ]
    )
    provider = build_provider(transport=transport, default_model="kling-video-3")
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    result = run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))

    assert isinstance(result.data, GeneratedVideo)
    assert result.data.provider_name == "kling"
    assert result.data.model == "kling-video-3"
    assert result.data.mime_type == "video/mp4"
    assert result.data.duration_seconds == 5.0
    assert result.data.payload_bytes == b"fake-video-bytes"
    assert result.data.request_id == "task_123"
    assert result.data.artifact.uri.startswith("kling://generated/video/task_123")
    assert "example.invalid" not in str(result.model_dump())


def test_missing_output_is_rejected_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed task without output should fail safely."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    transport = FakeKlingTransport(
        snapshots=[KlingTaskSnapshot(task_id="task_123", status=KlingTaskStatus.SUCCEEDED)]
    )
    provider = build_provider(transport=transport)
    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(VideoGenerationRequest(prompt="clip", duration_seconds=5.0)))


def test_auth_rate_limit_network_and_malformed_errors_are_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport errors should map cleanly into CreatorOS provider exceptions."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("creatoros.providers.kling.video.asyncio.sleep", fake_sleep)
    request = VideoGenerationRequest(prompt="clip", duration_seconds=5.0)

    auth_provider = build_provider(
        transport=FakeKlingTransport(submit_error=KlingAuthenticationTransportError("bad auth"))
    )
    with pytest.raises(ProviderAuthenticationError):
        run_async(auth_provider.generate(request))

    rate_limit_provider = build_provider(
        transport=FakeKlingTransport(submit_error=KlingRateLimitTransportError("slow down"))
    )
    with pytest.raises(ProviderRateLimitError):
        run_async(rate_limit_provider.generate(request))

    network_provider = build_provider(
        transport=FakeKlingTransport(submit_error=KlingNetworkTransportError("offline"))
    )
    with pytest.raises(ProviderUnavailableError):
        run_async(network_provider.generate(request))

    malformed_provider = build_provider(
        transport=FakeKlingTransport(submit_error=KlingMalformedResponseTransportError("bad schema"))
    )
    with pytest.raises(ProviderResponseError):
        run_async(malformed_provider.generate(request))


def test_registration_is_explicit_makes_zero_network_calls_and_mock_remains_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit Kling registration should not make calls and should preserve mock default resolution."""

    class StubSettings:
        kling_api_key = "kling-secret"
        default_video_model = "kling-video-model"
        default_video_provider = "mock"
        kling_video_timeout_seconds = 900.0
        kling_video_poll_interval_seconds = 5.0

    registry = create_provider_registry()
    transport = FakeKlingTransport()
    registry.register(MockVideoProvider())
    monkeypatch.setattr("creatoros.providers.kling.bootstrap.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    provider = register_kling_video_provider(registry, transport=transport)

    assert provider is registry.get("video", "kling")
    assert registry.contains("video", "kling")
    assert provider._timeout_seconds == 900.0
    assert provider._poll_interval_seconds == 5.0
    assert resolve_default_video_provider(registry).info.name == "mock"
    assert transport.submit_calls == []
    assert transport.poll_calls == []
    assert transport.download_calls == []


def test_kling_video_module_contains_no_forbidden_cross_boundary_integrations() -> None:
    """The Kling adapter shell should not pull in unrelated provider or publishing concerns."""

    source = Path("creatoros/providers/kling/video.py").read_text(encoding="utf-8")

    assert "OpenAI" not in source
    assert "ffmpeg" not in source.lower()
    assert "youtube" not in source.lower()
    assert "publish(" not in source
    assert "cloudinary" not in source.lower()
