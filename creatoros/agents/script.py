"""Provider-independent script agent integrations for CreatorOS."""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, field_validator

from creatoros.agents.research import ResearchExecutionOptions
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import GamingCTAOutput, GamingHookOutput, YouTubeShortsScriptOutput
from creatoros.prompts import GAMING_CTA, GAMING_HOOK, YOUTUBE_SHORTS_SCRIPT
from creatoros.services import LLMExecutionRequest, LLMExecutionService

TScriptOutput = TypeVar(
    "TScriptOutput",
    YouTubeShortsScriptOutput,
    GamingHookOutput,
    GamingCTAOutput,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values for script-agent inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingScriptGenerationRequest(CreatorOSModel):
    """Normalized application input for full short-form script generation."""

    title: str
    game: str
    topic: str
    angle: str
    hook_direction: str
    platform: str
    target_duration_seconds: int = Field(gt=0)
    source_summary: str

    @field_validator(
        "title",
        "game",
        "topic",
        "angle",
        "hook_direction",
        "platform",
        "source_summary",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingHookGenerationRequest(CreatorOSModel):
    """Normalized application input for gaming hook generation."""

    game: str
    title: str
    topic: str
    angle: str
    source_summary: str
    platform: str

    @field_validator("game", "title", "topic", "angle", "source_summary", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingCTAGenerationRequest(CreatorOSModel):
    """Normalized application input for gaming CTA generation."""

    game: str
    topic: str
    platform: str
    tone: str

    @field_validator("game", "topic", "platform", "tone")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingScriptAgent:
    """Application script agent that executes builtin script prompts through LLMExecutionService."""

    def __init__(self, llm_execution_service: LLMExecutionService) -> None:
        if not isinstance(llm_execution_service, LLMExecutionService):
            raise CreatorOSValidationError(
                "llm_execution_service must be an LLMExecutionService",
                code="agent_invalid_dependency",
                details={"dependency": "llm_execution_service"},
            )
        self.llm_execution_service = llm_execution_service

    async def generate_script(
        self,
        request: GamingScriptGenerationRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> YouTubeShortsScriptOutput:
        """Execute the builtin short-form script prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=YOUTUBE_SHORTS_SCRIPT,
            variables={
                "title": request.title,
                "game": request.game,
                "topic": request.topic,
                "angle": request.angle,
                "hook_direction": request.hook_direction,
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
                "source_summary": request.source_summary,
            },
            output_model_type=YouTubeShortsScriptOutput,
            execution_options=execution_options,
        )

    async def generate_hooks(
        self,
        request: GamingHookGenerationRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingHookOutput:
        """Execute the builtin gaming hook prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_HOOK,
            variables={
                "game": request.game,
                "title": request.title,
                "topic": request.topic,
                "angle": request.angle,
                "source_summary": request.source_summary,
                "platform": request.platform,
            },
            output_model_type=GamingHookOutput,
            execution_options=execution_options,
        )

    async def generate_cta(
        self,
        request: GamingCTAGenerationRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingCTAOutput:
        """Execute the builtin gaming CTA prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_CTA,
            variables={
                "game": request.game,
                "topic": request.topic,
                "platform": request.platform,
                "tone": request.tone,
            },
            output_model_type=GamingCTAOutput,
            execution_options=execution_options,
        )

    async def _execute_typed(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
        output_model_type: type[TScriptOutput],
        execution_options: ResearchExecutionOptions | None,
    ) -> TScriptOutput:
        """Execute one script prompt and require the expected typed parser output."""

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
                "script agent received an unexpected typed output model",
                code="agent_unexpected_output_model",
                details={
                    "prompt_name": prompt_name,
                    "expected_output_model": output_model_type.__name__,
                    "actual_output_model": type(result.output).__name__,
                },
            )
        return result.output


__all__ = [
    "GamingCTAGenerationRequest",
    "GamingHookGenerationRequest",
    "GamingScriptAgent",
    "GamingScriptGenerationRequest",
]
