"""Deterministic mock LLM provider implementations for CreatorOS."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from creatoros.core import CreatorOSValidationError
from creatoros.domain import generate_id
from creatoros.providers.base import (
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
        text_response: str = "Mock generated text.",
        structured_payload: dict[str, object] | None = None,
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
        self._text_response = text_response
        self._structured_payload = None if structured_payload is None else dict(structured_payload)

    async def generate_text(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Return deterministic text without exposing prompt content."""

        _validate_non_blank(prompt, field_name="prompt")
        return ProviderResult[str](
            data=self._text_response,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
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
            raise CreatorOSValidationError(
                "structured payload failed validation",
                code="provider_invalid_structured_payload",
                details={"response_model": response_model.__name__},
            ) from error

        return ProviderResult[TStructured](
            data=data,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
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
