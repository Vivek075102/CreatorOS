"""Bootstrap helpers for the CreatorOS OpenAI provider adapter."""

from __future__ import annotations

from creatoros.config import get_settings
from creatoros.providers.openai.image import (
    OpenAIImageProvider,
    _AsyncOpenAIImageClient,
)
from creatoros.providers.openai.llm import (
    DEFAULT_OPENAI_MODEL,
    OpenAILLMProvider,
    _AsyncOpenAIClient,
)
from creatoros.providers.openai.tts import (
    OpenAITTSProvider,
    _AsyncOpenAITTSClient,
)
from creatoros.providers.registry import ProviderRegistry


def register_openai_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    api_key: str | None = None,
    client: _AsyncOpenAIClient | None = None,
    default_model: str | None = None,
) -> OpenAILLMProvider:
    """Register one OpenAI LLM provider without making any network requests."""

    settings = get_settings()
    provider = OpenAILLMProvider(
        api_key=settings.openai_api_key if api_key is None else api_key,
        client=client,
        default_model=DEFAULT_OPENAI_MODEL if default_model is None else default_model,
        timeout_seconds=settings.provider_timeout_seconds,
    )
    registry.register(provider, replace=replace)
    return provider


def register_openai_image_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    api_key: str | None = None,
    client: _AsyncOpenAIImageClient | None = None,
    default_model: str | None = None,
) -> OpenAIImageProvider:
    """Register one OpenAI image provider without making any network requests."""

    settings = get_settings()
    provider = OpenAIImageProvider(
        api_key=settings.openai_api_key if api_key is None else api_key,
        client=client,
        default_model=settings.default_image_model if default_model is None else default_model,
        timeout_seconds=settings.openai_image_timeout_seconds,
        max_retries=0,
    )
    registry.register(provider, replace=replace)
    return provider


def register_openai_tts_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    api_key: str | None = None,
    client: _AsyncOpenAITTSClient | None = None,
    default_model: str | None = None,
) -> OpenAITTSProvider:
    """Register one OpenAI TTS provider without making any network requests."""

    settings = get_settings()
    provider = OpenAITTSProvider(
        api_key=settings.openai_api_key if api_key is None else api_key,
        client=client,
        default_model=settings.default_tts_model if default_model is None else default_model,
        timeout_seconds=settings.provider_timeout_seconds,
        max_retries=settings.provider_max_retries,
    )
    registry.register(provider, replace=replace)
    return provider


__all__ = [
    "register_openai_image_provider",
    "register_openai_provider",
    "register_openai_tts_provider",
]
