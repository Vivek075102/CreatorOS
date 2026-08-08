"""Provider-independent research agent integrations for CreatorOS."""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, field_validator

from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingKeywordExpansionOutput,
    GamingOpportunityEvaluationOutput,
    GamingTrendDiscoveryOutput,
)
from creatoros.prompts import (
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EXPAND_KEYWORDS,
)
from creatoros.services import LLMExecutionRequest, LLMExecutionService

TResearchOutput = TypeVar(
    "TResearchOutput",
    GamingTrendDiscoveryOutput,
    GamingOpportunityEvaluationOutput,
    GamingKeywordExpansionOutput,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values for research agent inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class ResearchExecutionOptions(CreatorOSModel):
    """Optional provider-neutral execution overrides for research-agent calls."""

    provider_name: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None

    @field_validator("provider_name", "model")
    @classmethod
    def validate_optional_text(cls, value: str | None, info) -> str | None:
        """Trim optional execution override identifiers."""

        if value is None:
            return None
        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float | None) -> float | None:
        """Require provider-neutral temperature bounds when supplied."""

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
        """Require positive timeouts when supplied."""

        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value


class GamingTrendDiscoveryRequest(CreatorOSModel):
    """Normalized application input for gaming trend discovery."""

    game: str
    topic: str
    research_signals: str
    platform: str
    target_duration_seconds: int = Field(gt=0)

    @field_validator("game", "topic", "research_signals", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingOpportunityEvaluationRequest(CreatorOSModel):
    """Normalized application input for gaming opportunity evaluation."""

    game: str
    title: str
    topic: str
    angle: str
    source_summary: str
    platform: str
    target_duration_seconds: int = Field(gt=0)

    @field_validator("game", "title", "topic", "angle", "source_summary", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_trend_discovery(
        cls,
        trend_output: GamingTrendDiscoveryOutput,
        *,
        platform: str,
        target_duration_seconds: int,
    ) -> GamingOpportunityEvaluationRequest:
        """Build an opportunity-evaluation request from one typed trend-discovery output."""

        return cls(
            game=trend_output.game,
            title=trend_output.title,
            topic=trend_output.topic,
            angle=trend_output.angle,
            source_summary=trend_output.source_summary,
            platform=platform,
            target_duration_seconds=target_duration_seconds,
        )


class GamingKeywordExpansionRequest(CreatorOSModel):
    """Normalized application input for gaming keyword expansion."""

    game: str
    topic: str
    seed_keywords: str
    platform: str

    @field_validator("game", "topic", "seed_keywords", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingResearchAgent:
    """Application research agent that executes builtin research prompts through LLMExecutionService."""

    def __init__(self, llm_execution_service: LLMExecutionService) -> None:
        if not isinstance(llm_execution_service, LLMExecutionService):
            raise CreatorOSValidationError(
                "llm_execution_service must be an LLMExecutionService",
                code="agent_invalid_dependency",
                details={"dependency": "llm_execution_service"},
            )
        self.llm_execution_service = llm_execution_service

    async def discover_trends(
        self,
        request: GamingTrendDiscoveryRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingTrendDiscoveryOutput:
        """Execute the builtin gaming trend-discovery prompt and return the typed research output."""

        return await self._execute_typed(
            prompt_name=GAMING_DISCOVER_TRENDS,
            variables={
                "game": request.game,
                "topic": request.topic,
                "research_signals": request.research_signals,
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
            },
            output_model_type=GamingTrendDiscoveryOutput,
            execution_options=execution_options,
        )

    async def evaluate_opportunity(
        self,
        request: GamingOpportunityEvaluationRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingOpportunityEvaluationOutput:
        """Execute the builtin gaming opportunity-evaluation prompt and return the typed output."""

        return await self._execute_typed(
            prompt_name=GAMING_EVALUATE_OPPORTUNITY,
            variables={
                "game": request.game,
                "title": request.title,
                "topic": request.topic,
                "angle": request.angle,
                "source_summary": request.source_summary,
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
            },
            output_model_type=GamingOpportunityEvaluationOutput,
            execution_options=execution_options,
        )

    async def expand_keywords(
        self,
        request: GamingKeywordExpansionRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingKeywordExpansionOutput:
        """Execute the builtin gaming keyword-expansion prompt and return the typed output."""

        return await self._execute_typed(
            prompt_name=GAMING_EXPAND_KEYWORDS,
            variables={
                "game": request.game,
                "topic": request.topic,
                "seed_keywords": request.seed_keywords,
                "platform": request.platform,
            },
            output_model_type=GamingKeywordExpansionOutput,
            execution_options=execution_options,
        )

    async def _execute_typed(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
        output_model_type: type[TResearchOutput],
        execution_options: ResearchExecutionOptions | None,
    ) -> TResearchOutput:
        """Execute one research prompt and require the expected typed parser output."""

        request = LLMExecutionRequest(
            prompt_name=prompt_name,
            variables=variables,
            provider_name=None if execution_options is None else execution_options.provider_name,
            model=None if execution_options is None else execution_options.model,
            temperature=None if execution_options is None else execution_options.temperature,
            max_output_tokens=None if execution_options is None else execution_options.max_output_tokens,
            timeout_seconds=None if execution_options is None else execution_options.timeout_seconds,
        )
        result = await self.llm_execution_service.execute(request)
        if not isinstance(result.output, output_model_type):
            raise CreatorOSValidationError(
                "research agent received an unexpected typed output model",
                code="agent_unexpected_output_model",
                details={
                    "prompt_name": prompt_name,
                    "expected_output_model": output_model_type.__name__,
                    "actual_output_model": type(result.output).__name__,
                },
            )
        return result.output


__all__ = [
    "GamingKeywordExpansionRequest",
    "GamingOpportunityEvaluationRequest",
    "GamingResearchAgent",
    "GamingTrendDiscoveryRequest",
    "ResearchExecutionOptions",
]
