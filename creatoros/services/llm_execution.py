"""Application-layer LLM execution service for prompt rendering and typed parsing."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter

from pydantic import Field, field_validator

from creatoros.config import Settings, get_settings
from creatoros.core import (
    ApplicationError,
    CreatorOSError,
    ProviderTypeMismatchError,
    wrap_exception,
)
from creatoros.domain import CreatorOSModel
from creatoros.observability import get_logger
from creatoros.parsing import ParserRegistry, build_builtin_parser_registry
from creatoros.prompts import (
    PromptDefinition,
    PromptRegistry,
    PromptRenderer,
    RenderedPrompt,
    create_builtin_prompt_registry,
)
from creatoros.providers import (
    LLMProvider,
    LLMRequest,
    LLMUsage,
    ProviderRegistry,
)
from creatoros.providers.mock import create_mock_provider_registry


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_string(value: str | None) -> str | None:
    """Trim optional strings and normalize blanks to ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _copy_mapping(value: Mapping[str, object] | dict[str, object] | None) -> dict[str, object]:
    """Return a deep defensive copy of a metadata-style mapping."""

    if value is None:
        return {}
    return deepcopy(dict(value))


class LLMExecutionRequest(CreatorOSModel):
    """Provider-independent application request for prompt-to-typed-output execution."""

    prompt_name: str
    prompt_version: int | None = None
    variables: dict[str, object] = Field(default_factory=dict)
    provider_name: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("prompt_name")
    @classmethod
    def validate_prompt_name(cls, value: str) -> str:
        """Reject blank prompt names."""

        return _validate_non_blank(value, field_name="prompt_name")

    @field_validator("prompt_version")
    @classmethod
    def validate_prompt_version(cls, value: int | None) -> int | None:
        """Require positive prompt versions when supplied."""

        if value is not None and value < 1:
            raise ValueError("prompt_version must be greater than or equal to 1")
        return value

    @field_validator("provider_name", "model")
    @classmethod
    def normalize_optional_identifiers(cls, value: str | None) -> str | None:
        """Trim optional provider and model identifiers."""

        return _normalize_optional_string(value)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float | None) -> float | None:
        """Validate provider-neutral temperature values when supplied."""

        if value is not None and not 0.0 <= value <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value

    @field_validator("max_output_tokens")
    @classmethod
    def validate_max_output_tokens(cls, value: int | None) -> int | None:
        """Require positive token limits when supplied."""

        if value is not None and value <= 0:
            raise ValueError("max_output_tokens must be greater than zero")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: float | None) -> float | None:
        """Require positive provider-neutral timeouts when supplied."""

        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value

    @field_validator("variables", "metadata", mode="before")
    @classmethod
    def copy_mapping_fields(cls, value: object) -> dict[str, object]:
        """Copy mutable request mappings defensively."""

        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("value must be a mapping")
        return _copy_mapping(value)


class LLMExecutionResult[TOutput: CreatorOSModel](CreatorOSModel):
    """Serializable typed result for one full prompt-to-parser LLM execution."""

    prompt_name: str
    prompt_version: int
    provider_name: str
    model: str
    output: TOutput
    usage: LLMUsage | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("prompt_name", "provider_name", "model")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Reject blank identifiers in execution results."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("prompt_version")
    @classmethod
    def validate_prompt_version(cls, value: int) -> int:
        """Require positive prompt versions."""

        if value < 1:
            raise ValueError("prompt_version must be greater than or equal to 1")
        return value

    @field_validator("output")
    @classmethod
    def copy_output_model(cls, value: TOutput) -> TOutput:
        """Copy typed parsed output defensively."""

        return value.model_copy(deep=True)

    @field_validator("usage")
    @classmethod
    def copy_usage_model(cls, value: LLMUsage | None) -> LLMUsage | None:
        """Copy normalized usage metadata defensively."""

        if value is None:
            return None
        return value.model_copy(deep=True)

    @field_validator("metadata", mode="before")
    @classmethod
    def copy_metadata(cls, value: object) -> dict[str, object]:
        """Copy mutable metadata defensively."""

        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("metadata must be a mapping")
        return _copy_mapping(value)


class LLMExecutionService:
    """Application service that orchestrates prompt rendering, provider execution, and parsing."""

    def __init__(
        self,
        prompt_registry: PromptRegistry,
        parser_registry: ParserRegistry,
        provider_registry: ProviderRegistry,
        settings: Settings,
        *,
        prompt_renderer: PromptRenderer | None = None,
    ) -> None:
        self.prompt_registry = prompt_registry
        self.parser_registry = parser_registry
        self.provider_registry = provider_registry
        self.settings = settings
        self.prompt_renderer = PromptRenderer() if prompt_renderer is None else prompt_renderer
        self.logger = get_logger("services.llm_execution")

    async def execute(
        self,
        request: LLMExecutionRequest,
    ) -> LLMExecutionResult[CreatorOSModel]:
        """Execute the full prompt-to-typed-output path through existing CreatorOS boundaries."""

        started_at = perf_counter()
        definition = self._resolve_prompt_definition(request)
        provider_name = request.provider_name or self.settings.default_llm_provider
        model_name = request.model or self.settings.default_llm_model

        self.logger.info(
            "llm_execution_started",
            prompt_name=definition.name,
            prompt_version=definition.version,
            provider_name=provider_name,
            model=model_name,
        )

        try:
            rendered_prompt = self.prompt_renderer.render(definition, request.variables)
            provider = self.provider_registry.get("llm", provider_name)
            if not isinstance(provider, LLMProvider):
                raise ProviderTypeMismatchError("llm", provider_name.strip().lower(), "LLMProvider")
            llm_request = self._build_llm_request(rendered_prompt, request, model_name)
            llm_response = await provider.generate(llm_request)
            parsed_output = self.parser_registry.parse(definition.name, llm_response.text)
        except CreatorOSError as error:
            self.logger.exception(
                "llm_execution_failed",
                prompt_name=definition.name,
                prompt_version=definition.version,
                provider_name=provider_name,
                model=model_name,
                error_type=type(error).__name__,
                error_code=error.code,
                retryable=error.retryable,
            )
            raise
        except Exception as error:
            wrapped_error = wrap_exception(
                error,
                message="LLM execution service failed",
                exception_type=ApplicationError,
                code="llm_execution_failed",
                details={
                    "prompt_name": definition.name,
                    "prompt_version": definition.version,
                    "provider_name": provider_name,
                    "model": model_name,
                },
            )
            self.logger.exception(
                "llm_execution_failed",
                prompt_name=definition.name,
                prompt_version=definition.version,
                provider_name=provider_name,
                model=model_name,
                error_type=type(wrapped_error).__name__,
                error_code=wrapped_error.code,
                retryable=wrapped_error.retryable,
            )
            raise wrapped_error from error

        result = LLMExecutionResult[CreatorOSModel](
            prompt_name=definition.name,
            prompt_version=definition.version,
            provider_name=llm_response.provider_name,
            model=llm_response.model,
            output=parsed_output,
            usage=llm_response.usage,
            finish_reason=llm_response.finish_reason,
            request_id=llm_response.request_id,
            metadata={
                "output_model_type": type(parsed_output).__name__,
                "provider_metadata": dict(llm_response.metadata),
            },
        )

        duration_ms = int(max((perf_counter() - started_at) * 1000, 0.0))
        usage = llm_response.usage
        self.logger.info(
            "llm_execution_completed",
            prompt_name=result.prompt_name,
            prompt_version=result.prompt_version,
            provider_name=result.provider_name,
            model=result.model,
            output_model_type=type(result.output).__name__,
            duration_ms=duration_ms,
            request_id=result.request_id,
            input_tokens=None if usage is None else usage.input_tokens,
            output_tokens=None if usage is None else usage.output_tokens,
            total_tokens=None if usage is None else usage.total_tokens,
        )
        return result

    def _resolve_prompt_definition(self, request: LLMExecutionRequest) -> PromptDefinition:
        """Resolve the target prompt definition by stable logical name and optional version."""

        return self.prompt_registry.get(
            request.prompt_name,
            version=request.prompt_version,
        )

    def _build_llm_request(
        self,
        rendered_prompt: RenderedPrompt,
        request: LLMExecutionRequest,
        model_name: str,
    ) -> LLMRequest:
        """Convert a rendered prompt into the provider-neutral LLM request contract."""

        return LLMRequest(
            messages=[message.model_copy(deep=True) for message in rendered_prompt.messages],
            model=_validate_non_blank(model_name, field_name="model"),
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            timeout_seconds=request.timeout_seconds,
            metadata=_copy_mapping(request.metadata),
        )


def create_llm_execution_service(
    *,
    prompt_registry: PromptRegistry | None = None,
    parser_registry: ParserRegistry | None = None,
    provider_registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
    prompt_renderer: PromptRenderer | None = None,
) -> LLMExecutionService:
    """Create a safe default LLM execution service using builtin prompt and parser registries."""

    resolved_settings = get_settings() if settings is None else settings
    resolved_prompt_registry = (
        create_builtin_prompt_registry(base_dir=resolved_settings.prompts_dir)
        if prompt_registry is None
        else prompt_registry
    )
    resolved_parser_registry = (
        build_builtin_parser_registry()
        if parser_registry is None
        else parser_registry
    )
    resolved_provider_registry = (
        create_mock_provider_registry()
        if provider_registry is None
        else provider_registry
    )
    return LLMExecutionService(
        resolved_prompt_registry,
        resolved_parser_registry,
        resolved_provider_registry,
        resolved_settings,
        prompt_renderer=prompt_renderer,
    )


__all__ = [
    "LLMExecutionRequest",
    "LLMExecutionResult",
    "LLMExecutionService",
    "create_llm_execution_service",
]
