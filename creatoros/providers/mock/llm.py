"""Deterministic mock LLM provider implementations for CreatorOS."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from creatoros.core import CreatorOSValidationError, ProviderResponseError
from creatoros.prompts.enums import PromptRole
from creatoros.prompts.models import PromptMessage
from creatoros.providers.base import (
    LLMCapabilities,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name},
        )
    return normalized_value


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class MockLLMProvider(MockProviderBase):
    """Deterministic mock provider for text and structured generation."""

    def __init__(
        self,
        *,
        response_text: str | None = None,
        text_response: str = "Mock generated text.",
        structured_payload: dict[str, object] | None = None,
        model_name: str = "mock-model",
        is_healthy: bool = True,
    ) -> None:
        super().__init__(
            name="mock",
            provider_type="llm",
            capabilities={
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.STRUCTURED_GENERATION,
            },
            is_healthy=is_healthy,
        )
        self._response_text = text_response if response_text is None else response_text
        self._structured_payload = None if structured_payload is None else dict(structured_payload)
        self._model_name = _validate_non_blank(model_name, field_name="model_name")
        self._llm_capabilities = LLMCapabilities(
            supports_temperature=True,
            supports_max_output_tokens=True,
            supports_system_messages=True,
            supports_structured_text=True,
        )

    @property
    def llm_capabilities(self) -> LLMCapabilities:
        """Return deterministic mock LLM capability flags."""

        return self._llm_capabilities.model_copy(deep=True)

    async def generate(
        self,
        request: LLMRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> LLMResponse:
        """Return a normalized deterministic LLM response without side effects."""

        del context
        input_tokens = _count_tokens([message.content for message in request.messages])
        output_tokens = _count_tokens([self._response_text])
        return LLMResponse(
            text=self._response_text,
            provider_name=self.info.name,
            model=request.model,
            finish_reason="stop",
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            request_id="mock_request",
        )

    async def generate_text(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Return deterministic text through the normalized request boundary."""

        request = LLMRequest(
            messages=[PromptMessage(role=PromptRole.USER, content=_validate_non_blank(prompt, field_name="prompt"))],
            model=self._model_name,
            timeout_seconds=context.timeout_seconds if context is not None else None,
        )
        response = await self.generate(request, context=context)
        return ProviderResult[str](
            data=response.text,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=response.request_id,
        )

    async def generate_structured[TStructured: BaseModel](
        self,
        prompt: str,
        *,
        response_model: type[TStructured],
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[TStructured]:
        """Return deterministic structured output validated against the requested model."""

        _validate_non_blank(prompt, field_name="prompt")
        payload = self._build_structured_payload(response_model)

        try:
            data = response_model.model_validate(payload)
        except ValidationError as error:
            raise ProviderResponseError(
                "provider response could not be normalized into the requested structured model",
                code="provider_response_invalid",
                details={"response_model": response_model.__name__},
            ) from error

        return ProviderResult[TStructured](
            data=data,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id="mock_request",
        )

    def _build_structured_payload[TStructured: BaseModel](
        self,
        response_model: type[TStructured],
    ) -> dict[str, object]:
        """Return a deterministic payload for the requested structured response model."""

        if self._structured_payload is not None:
            return dict(self._structured_payload)

        model_fields = response_model.model_fields
        if len(model_fields) != 1:
            raise CreatorOSValidationError(
                "structured_payload is required for this response model",
                code="provider_structured_payload_required",
                details={"response_model": response_model.__name__},
            )

        field_name, field_info = next(iter(model_fields.items()))
        annotation = field_info.annotation
        if annotation is str:
            return {field_name: "mock"}
        if annotation is int:
            return {field_name: 1}
        if annotation is float:
            return {field_name: 1.0}
        if annotation is bool:
            return {field_name: True}

        raise CreatorOSValidationError(
            "structured_payload is required for this response model",
            code="provider_structured_payload_required",
            details={"response_model": response_model.__name__},
        )


__all__ = ["MockLLMProvider"]


def _count_tokens(texts: list[str] | tuple[str, ...] | object) -> int:
    """Return a simple deterministic token estimate for mock usage metadata."""

    if not isinstance(texts, list | tuple):
        raise TypeError("texts must be a list or tuple of strings")
    total = 0
    for text in texts:
        if not isinstance(text, str):
            raise TypeError("texts must contain only strings")
        total += len(text.split())
    return total
