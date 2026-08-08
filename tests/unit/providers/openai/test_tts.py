"""Unit tests for the CreatorOS OpenAI TTS provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.providers import (
    GeneratedAudio,
    ProviderCapability,
    TTSGenerationRequest,
    TTSProvider,
    create_provider_registry,
    resolve_default_tts_provider,
)
from creatoros.providers.mock import MockTTSProvider
from creatoros.providers.openai import (
    DEFAULT_OPENAI_TTS_PROVIDER_NAME,
    OpenAITTSProvider,
    register_openai_tts_provider,
)


class FakeBinaryResponse:
    """Minimal fake OpenAI binary response wrapper for TTS tests."""

    def __init__(
        self,
        *,
        content: bytes = b"fake-audio-bytes",
        request_id: str = "req_tts_123",
        content_type: str = "audio/mpeg",
    ) -> None:
        self.response = httpx.Response(
            200,
            headers={"content-type": content_type, "x-request-id": request_id},
            content=content,
        )
        self._request_id = request_id

    async def aread(self) -> bytes:
        return self.response.content


@dataclass
class FakeSpeechClient:
    """Simple async fake that records the most recent TTS request."""

    response: object | None = None
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def create(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("response must be configured for this fake")
        return self.response


@dataclass
class FakeAudioClient:
    """Simple audio client exposing the speech interface."""

    speech: FakeSpeechClient


@dataclass
class FakeOpenAITTSClient:
    """Simple injected client exposing the OpenAI audio interface."""

    audio: FakeAudioClient


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
    client: FakeOpenAITTSClient | None = None,
    api_key: str | None = None,
    default_model: str | None = "gpt-4o-mini-tts",
) -> OpenAITTSProvider:
    """Create a TTS adapter with explicit local defaults for tests."""

    return OpenAITTSProvider(
        client=client,
        api_key=api_key,
        default_model=default_model,
        timeout_seconds=30.0,
        max_retries=0,
    )


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in unit tests without async plugins."""

    return asyncio.run(coro)


def test_openai_tts_provider_satisfies_runtime_tts_protocol() -> None:
    """The adapter should satisfy the runtime TTS provider contract."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )

    assert isinstance(provider, TTSProvider)


def test_fake_client_construction_works_without_api_key() -> None:
    """Fake-client tests should not require a configured API key."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse()))),
        api_key=None,
    )

    assert run_async(provider.health_check()) is True


def test_missing_api_key_fails_safely_when_real_client_is_needed() -> None:
    """Generating without an injected client or API key should fail safely."""

    provider = build_provider(client=None, api_key=None)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Speak this", voice="alloy")))

    assert exc_info.value.code == "provider_authentication_missing"
    assert exc_info.value.details == {"provider_name": DEFAULT_OPENAI_TTS_PROVIDER_NAME}


def test_provider_info_exposes_tts_only_identity_without_api_key() -> None:
    """Provider metadata should identify only the TTS capability."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )

    assert provider.info.name == "openai-tts"
    assert provider.info.provider_type == "voice"
    assert provider.info.capabilities == {ProviderCapability.VOICE_GENERATION}
    assert "api_key" not in provider.info.metadata


def test_generate_translates_request_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter should translate the request and normalize the audio result."""

    fake_logger = FakeLogger()
    fake_speech = FakeSpeechClient(response=FakeBinaryResponse())
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))
    monkeypatch.setattr("creatoros.providers.openai.tts._LOGGER", fake_logger)
    request = TTSGenerationRequest(text="Speak exactly this", voice="alloy", speed=1.1)

    result = run_async(provider.generate(request))

    assert isinstance(result.data, GeneratedAudio)
    assert result.provider.name == "openai-tts"
    assert result.data.provider_name == "openai-tts"
    assert result.data.model == "gpt-4o-mini-tts"
    assert result.data.mime_type == "audio/mpeg"
    assert result.data.voice == "alloy"
    assert result.data.request_id == "req_tts_123"
    assert result.data.estimated_duration_seconds is None
    assert result.data.artifact.uri.startswith("openai-tts://generated/")
    assert result.data.artifact.metadata["provider_reference_kind"] == "temporary"
    assert result.data.metadata["transient_source"] == "binary"
    assert result.data.payload_bytes == b"fake-audio-bytes"
    assert result.usage is None
    assert fake_speech.calls == [
        {
            "input": "Speak exactly this",
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "response_format": "mp3",
            "timeout": 30.0,
            "speed": 1.1,
        }
    ]
    dumped = str(result.model_dump())
    assert "fake-audio-bytes" not in dumped
    assert "Speak exactly this" not in dumped
    assert all("text" not in payload and "input" not in payload for _, payload in fake_logger.infos)


def test_generate_uses_default_timeout_when_no_context_override() -> None:
    """The provider default timeout should flow through when no context override is supplied."""

    fake_speech = FakeSpeechClient(response=FakeBinaryResponse())
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))

    run_async(provider.generate(TTSGenerationRequest(text="Narrate", voice="nova")))

    assert fake_speech.calls[0]["timeout"] == 30.0


def test_unsupported_request_values_are_rejected_safely() -> None:
    """Unsupported provider-neutral values should fail clearly for this adapter."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )

    with pytest.raises(CreatorOSValidationError) as language_error:
        run_async(provider.generate(TTSGenerationRequest(text="Narrate", voice="alloy", language="en")))
    with pytest.raises(CreatorOSValidationError) as missing_voice_error:
        run_async(provider.generate(TTSGenerationRequest(text="Narrate")))
    with pytest.raises(CreatorOSValidationError) as unsupported_voice_error:
        run_async(provider.generate(TTSGenerationRequest(text="Narrate", voice="robot")))

    assert language_error.value.details["field"] == "language"
    assert missing_voice_error.value.details["field"] == "voice"
    assert unsupported_voice_error.value.details["field"] == "voice"


def test_request_object_is_not_mutated() -> None:
    """Generation should leave the caller's request model unchanged."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )
    request = TTSGenerationRequest(text="Preserve this", voice="sage", speed=0.9)
    before = request.model_dump()

    run_async(provider.generate(request))

    assert request.model_dump() == before


def test_missing_audio_output_is_rejected_safely() -> None:
    """Responses without audio bytes should raise a typed provider response error."""

    provider = build_provider(
        client=FakeOpenAITTSClient(
            FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse(content=b"")))
        )
    )

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(TTSGenerationRequest(text="Missing bytes", voice="ash")))


def test_malformed_audio_output_is_rejected_safely() -> None:
    """Responses without a readable HTTP response should raise a typed error."""

    class BrokenBinaryResponse:
        async def aread(self) -> bytes:
            return b"audio"

    provider = build_provider(
        client=FakeOpenAITTSClient(
            FakeAudioClient(FakeSpeechClient(response=BrokenBinaryResponse()))
        )
    )

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(TTSGenerationRequest(text="Broken", voice="echo")))


def test_duration_absent_is_handled_safely() -> None:
    """The adapter should not invent an actual duration when the provider gives none."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )

    result = run_async(provider.generate(TTSGenerationRequest(text="No duration", voice="verse")))

    assert result.data.estimated_duration_seconds is None
    assert result.data.metadata["duration_provided"] is False


def test_payload_bytes_remain_ephemeral_and_excluded_from_serialization() -> None:
    """Binary payload bytes should remain available but excluded from normal model dumps."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )

    result = run_async(provider.generate(TTSGenerationRequest(text="No leaks", voice="verse")))

    dumped = result.data.model_dump()

    assert result.data.payload_bytes == b"fake-audio-bytes"
    assert "payload_bytes" not in dumped


def test_auth_errors_are_translated_without_secret_or_text_leakage() -> None:
    """Authentication failures should map to typed auth errors safely."""

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
    response = httpx.Response(401, request=request)
    fake_speech = FakeSpeechClient(
        error=openai.AuthenticationError(
            message="bad auth key sk-secret",
            response=response,
            body={"error": "bad"},
        )
    )
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Sensitive narration", voice="alloy")))

    assert exc_info.value.retryable is False
    assert "sk-secret" not in str(exc_info.value)
    assert "Sensitive narration" not in str(exc_info.value.details)


def test_rate_limit_errors_are_translated() -> None:
    """Rate-limit failures should map to the CreatorOS provider hierarchy."""

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
    response = httpx.Response(429, request=request)
    fake_speech = FakeSpeechClient(
        error=openai.RateLimitError("rate limited", response=response, body=None)
    )
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))

    with pytest.raises(ProviderRateLimitError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Castle lore", voice="nova")))

    assert exc_info.value.retryable is True


def test_timeout_errors_are_translated() -> None:
    """Timeout failures should become normalized timeout errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
    fake_speech = FakeSpeechClient(error=openai.APITimeoutError(request))
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))

    with pytest.raises(ProviderTimeoutError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Timeout", voice="nova")))

    assert exc_info.value.retryable is True


def test_connection_errors_are_translated() -> None:
    """Connection failures should become provider unavailable errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
    fake_speech = FakeSpeechClient(
        error=openai.APIConnectionError(message="no route", request=request)
    )
    provider = build_provider(client=FakeOpenAITTSClient(FakeAudioClient(fake_speech)))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Island", voice="nova")))

    assert exc_info.value.retryable is True


def test_unexpected_failures_are_translated_safely() -> None:
    """Unexpected failures should become safe normalized provider errors."""

    provider = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(error=RuntimeError("payload"))))
    )

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.generate(TTSGenerationRequest(text="Do not leak me", voice="alloy")))

    assert exc_info.value.code == "provider_response_invalid"
    assert "Do not leak me" not in str(exc_info.value.details)


def test_health_check_is_local_and_requires_model_and_credentials_or_client() -> None:
    """Health should remain a local readiness check with zero network calls."""

    ready_with_client = build_provider(
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse())))
    )
    ready_with_api_key = build_provider(client=None, api_key="sk-test")
    missing_model = build_provider(client=None, api_key="sk-test", default_model=None)

    assert run_async(ready_with_client.health_check()) is True
    assert run_async(ready_with_api_key.health_check()) is True
    assert run_async(missing_model.health_check()) is False


def test_register_openai_tts_provider_registers_explicitly_without_changing_mock_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit TTS registration should work while mock remains the configured default."""

    class StubSettings:
        openai_api_key = "sk-test"
        default_tts_model = "gpt-4o-mini-tts"
        default_tts_provider = "mock"
        provider_timeout_seconds = 30.0
        provider_max_retries = 3

    registry = create_provider_registry()
    registry.register(MockTTSProvider())
    monkeypatch.setattr("creatoros.providers.openai.bootstrap.get_settings", lambda: StubSettings())
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    provider = register_openai_tts_provider(
        registry,
        client=FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient(response=FakeBinaryResponse()))),
    )

    assert provider is registry.get("voice", "openai-tts")
    assert registry.contains("voice", "openai-tts")
    assert resolve_default_tts_provider(registry).info.name == "mock"


def test_openai_tts_module_contains_no_file_or_pipeline_side_effects() -> None:
    """The adapter module should stay focused on provider translation only."""

    module_source = Path("creatoros/providers/openai/tts.py").read_text(encoding="utf-8")

    assert "GamingMediaAgent" not in module_source
    assert "GamingContentPipeline" not in module_source
    assert "ElevenLabs" not in module_source
    assert "ffmpeg" not in module_source.lower()
    assert "stream_to_file" not in module_source
    assert "write_to_file" not in module_source
