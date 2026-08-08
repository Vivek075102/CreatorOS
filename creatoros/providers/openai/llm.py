"""OpenAI LLM provider adapter for CreatorOS."""

from __future__ import annotations

from typing import Protocol, TypeVar, cast

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from creatoros.config import get_settings
from creatoros.core import (
    CreatorOSValidationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.prompts.enums import PromptRole
from creatoros.prompts.models import PromptMessage
from creatoros.providers.base import (
    LLMCapabilities,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)

TStructured = TypeVar("TStructured", bound=BaseModel)

DEFAULT_OPENAI_MODEL = "gpt-5-mini"
_OPENAI_PROVIDER_NAME = "openai"
_OPENAI_PROVIDER_TYPE = "llm"


class _ResponsesClient(Protocol):
    """Minimal async responses client contract used by the adapter."""

    async def create(self, **kwargs: object) -> object:
        """Create one provider response."""


class _AsyncOpenAIClient(Protocol):
    """Minimal async OpenAI client contract used by the adapter."""

    @property
    def responses(self) -> _ResponsesClient:
        """Return the responses API client."""


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name, "provider_name": _OPENAI_PROVIDER_NAME},
        )
    return normalized_value


def _safe_request_id(response: object) -> str | None:
    """Return a request identifier when the SDK exposes one."""

    request_id = getattr(response, "_request_id", None)
    if isinstance(request_id, str):
        normalized_request_id = request_id.strip()
        if normalized_request_id:
            return normalized_request_id
    return None


def _normalize_finish_reason(response: object) -> str | None:
    """Return a provider-neutral finish reason when one can be inferred."""

    status = getattr(response, "status", None)
    if not isinstance(status, str):
        return None

    normalized_status = status.strip().lower()
    if normalized_status == "completed":
        return "stop"
    if not normalized_status:
        return None
    return normalized_status


def _normalize_usage(response: object) -> LLMUsage | None:
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

    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _extract_text(response: object) -> str:
    """Extract response text without leaking SDK types past the adapter boundary."""

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    raise ProviderResponseError(
        "provider response did not contain readable text output",
        code="provider_response_invalid",
        details={"provider_name": _OPENAI_PROVIDER_NAME},
    )


def _normalize_metadata(response: object) -> dict[str, object]:
    """Return a safe, minimal metadata payload from the SDK response."""

    metadata: dict[str, object] = {}

    status = getattr(response, "status", None)
    if isinstance(status, str) and status.strip():
        metadata["status"] = status.strip()

    response_id = getattr(response, "id", None)
    if isinstance(response_id, str) and response_id.strip():
        metadata["response_id"] = response_id.strip()

    return metadata


def _to_openai_input(messages: list[PromptMessage]) -> list[dict[str, object]]:
    """Translate provider-independent prompt messages to OpenAI Responses input."""

    translated_messages: list[dict[str, object]] = []
    for message in messages:
        translated_messages.append(
            {
                "role": message.role.value,
                "content": [{"type": "input_text", "text": message.content}],
            }
        )
    return translated_messages


def _zero_cost_usage() -> ProviderUsage:
    """Return a placeholder usage record for compatibility methods."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class OpenAILLMProvider:
    """Provider adapter that normalizes OpenAI Responses API calls for CreatorOS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: _AsyncOpenAIClient | None = None,
        default_model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._info = ProviderInfo(
            name=_OPENAI_PROVIDER_NAME,
            provider_type=_OPENAI_PROVIDER_TYPE,
            capabilities={
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.STRUCTURED_GENERATION,
            },
            version="1.0",
        )
        self._default_model = _validate_non_blank(default_model, field_name="default_model")
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
                details={"field": "timeout_seconds", "provider_name": _OPENAI_PROVIDER_NAME},
            )
        if self._max_retries < 0:
            raise CreatorOSValidationError(
                "max_retries must be zero or greater",
                code="provider_invalid_input",
                details={"field": "max_retries", "provider_name": _OPENAI_PROVIDER_NAME},
            )

        normalized_api_key = None if api_key is None else api_key.strip()
        if normalized_api_key == "":
            normalized_api_key = None
        self._api_key = normalized_api_key
        self._client: _AsyncOpenAIClient | None = client
        self._llm_capabilities = LLMCapabilities(
            supports_temperature=True,
            supports_max_output_tokens=True,
            supports_system_messages=True,
            supports_structured_text=False,
            metadata={"api_style": "responses"},
        )

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the OpenAI adapter."""

        return self._info.model_copy(deep=True)

    @property
    def llm_capabilities(self) -> LLMCapabilities:
        """Return provider-neutral LLM feature flags for this adapter."""

        return self._llm_capabilities.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return local readiness without making a live network request."""

        return self._client is not None or self._api_key is not None

    async def generate(
        self,
        request: LLMRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> LLMResponse:
        """Execute one normalized Responses API call and return a normalized LLM response."""

        client = self._get_client()
        timeout_seconds = request.timeout_seconds
        if timeout_seconds is None and context is not None:
            timeout_seconds = context.timeout_seconds
        if timeout_seconds is None:
            timeout_seconds = self._timeout_seconds

        request_kwargs: dict[str, object] = {
            "model": request.model,
            "input": _to_openai_input(request.messages),
            "timeout": timeout_seconds,
        }
        if request.temperature is not None:
            request_kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            request_kwargs["max_output_tokens"] = request.max_output_tokens

        if request.metadata:
            request_kwargs["metadata"] = {
                key: value
                for key, value in request.metadata.items()
                if isinstance(key, str) and isinstance(value, str | int | float | bool)
            }

        try:
            raw_response = await client.responses.create(**request_kwargs)
        except Exception as error:
            raise self._translate_error(error, model=request.model) from error

        text = _extract_text(raw_response)
        response_model = getattr(raw_response, "model", None)
        normalized_model = response_model if isinstance(response_model, str) and response_model.strip() else request.model
        return LLMResponse(
            text=text,
            provider_name=self.info.name,
            model=normalized_model,
            finish_reason=_normalize_finish_reason(raw_response),
            usage=_normalize_usage(raw_response),
            request_id=_safe_request_id(raw_response),
            metadata=_normalize_metadata(raw_response),
        )

    async def generate_text(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Execute simple compatibility text generation through the normalized boundary."""

        request = LLMRequest(
            messages=[
                PromptMessage(
                    role=PromptRole.USER,
                    content=_validate_non_blank(prompt, field_name="prompt"),
                )
            ],
            model=self._default_model,
            timeout_seconds=context.timeout_seconds if context is not None else None,
        )
        response = await self.generate(request, context=context)
        return ProviderResult[str](
            data=response.text,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=response.request_id,
            metadata={"model": response.model},
        )

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[TStructured],
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[TStructured]:
        """Attempt minimal JSON-based structured validation for compatibility paths."""

        text_result = await self.generate_text(prompt, context=context)
        try:
            data = response_model.model_validate_json(text_result.data)
        except ValidationError as error:
            raise ProviderResponseError(
                "provider response could not be normalized into the requested structured model",
                code="provider_response_invalid",
                details={
                    "provider_name": _OPENAI_PROVIDER_NAME,
                    "response_model": response_model.__name__,
                },
            ) from error

        return ProviderResult[TStructured](
            data=data,
            provider=self.info,
            usage=text_result.usage,
            request_id=text_result.request_id,
            metadata=dict(text_result.metadata),
        )

    def _get_client(self) -> _AsyncOpenAIClient:
        """Return the injected client or create one from safe configuration."""

        if self._client is not None:
            return self._client

        if self._api_key is None:
            raise ProviderAuthenticationError(
                "OpenAI API key is not configured",
                code="provider_authentication_missing",
                details={"provider_name": _OPENAI_PROVIDER_NAME},
                retryable=False,
            )

        self._client = cast(
            _AsyncOpenAIClient,
            AsyncOpenAI(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=self._max_retries,
            ),
        )
        return self._client

    def _translate_error(self, error: Exception, *, model: str) -> Exception:
        """Translate vendor SDK failures into typed CreatorOS provider exceptions."""

        safe_details: dict[str, object] = {
            "provider_name": _OPENAI_PROVIDER_NAME,
            "model": model,
        }

        if isinstance(error, APITimeoutError | TimeoutError | httpx.TimeoutException):
            return ProviderTimeoutError(
                "OpenAI request timed out",
                code="provider_timeout",
                details=safe_details,
            )

        if isinstance(error, APIConnectionError | httpx.NetworkError):
            return ProviderUnavailableError(
                "OpenAI is unavailable",
                code="provider_unavailable",
                details=safe_details,
            )

        if error.__class__.__name__ == "AuthenticationError":
            return ProviderAuthenticationError(
                "OpenAI authentication failed",
                code="provider_authentication_failed",
                details=safe_details,
                retryable=False,
            )

        if error.__class__.__name__ == "RateLimitError":
            return ProviderRateLimitError(
                "OpenAI rate limit encountered",
                code="provider_rate_limited",
                details=safe_details,
            )

        if isinstance(error, APIStatusError):
            status_code = getattr(error, "status_code", None)
            if isinstance(status_code, int):
                safe_details["status_code"] = status_code

            request_id = _safe_request_id(error.response)
            if request_id is not None:
                safe_details["request_id"] = request_id

            if isinstance(status_code, int) and status_code >= 500:
                return ProviderUnavailableError(
                    "OpenAI returned a server error",
                    code="provider_unavailable",
                    details=safe_details,
                )

            return ProviderResponseError(
                "OpenAI returned an invalid response",
                code="provider_response_invalid",
                details=safe_details,
            )

        return ProviderResponseError(
            "OpenAI request failed unexpectedly",
            code="provider_response_invalid",
            details=safe_details,
        )


__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "OpenAILLMProvider",
]
