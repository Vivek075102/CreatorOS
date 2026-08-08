"""Provider-independent storyboard agent integrations for CreatorOS."""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, field_validator

from creatoros.agents.research import ResearchExecutionOptions
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    STORYBOARD_SCENE_BREAKDOWN,
    STORYBOARD_TIMING_REVIEW,
    STORYBOARD_VISUAL_DIRECTION,
)
from creatoros.services import LLMExecutionRequest, LLMExecutionService

TStoryboardOutput = TypeVar(
    "TStoryboardOutput",
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values for storyboard-agent inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingStoryboardSceneBreakdownRequest(CreatorOSModel):
    """Normalized application input for storyboard scene breakdown generation."""

    title: str
    game: str
    platform: str
    hook: str
    body: str
    ending: str
    call_to_action: str
    target_duration_seconds: int = Field(gt=0)

    @field_validator("title", "game", "platform", "hook", "body", "ending", "call_to_action")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_script(
        cls,
        script_output: YouTubeShortsScriptOutput,
        *,
        game: str,
        platform: str,
    ) -> GamingStoryboardSceneBreakdownRequest:
        """Build a scene-breakdown request from one typed script output."""

        return cls(
            title=script_output.title,
            game=game,
            platform=platform,
            hook=script_output.hook,
            body=script_output.body,
            ending=script_output.ending,
            call_to_action=script_output.call_to_action,
            target_duration_seconds=script_output.estimated_duration_seconds,
        )


class GamingStoryboardTimingReviewRequest(CreatorOSModel):
    """Normalized application input for storyboard timing review."""

    title: str
    scene_summary: str
    target_duration_seconds: int = Field(gt=0)
    platform: str

    @field_validator("title", "scene_summary", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingStoryboardVisualDirectionRequest(CreatorOSModel):
    """Normalized application input for storyboard visual-direction generation."""

    game: str
    scene_number: int = Field(gt=0)
    scene_purpose: str
    script_beat: str
    visual_summary: str
    platform: str
    duration_seconds: float = Field(gt=0)

    @field_validator("game", "scene_purpose", "script_beat", "visual_summary", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class GamingStoryboardAgent:
    """Application storyboard agent that executes builtin storyboard prompts through LLMExecutionService."""

    def __init__(self, llm_execution_service: LLMExecutionService) -> None:
        if not isinstance(llm_execution_service, LLMExecutionService):
            raise CreatorOSValidationError(
                "llm_execution_service must be an LLMExecutionService",
                code="agent_invalid_dependency",
                details={"dependency": "llm_execution_service"},
            )
        self.llm_execution_service = llm_execution_service

    async def break_down_scenes(
        self,
        request: GamingStoryboardSceneBreakdownRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> StoryboardSceneBreakdownOutput:
        """Execute the builtin storyboard scene-breakdown prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=STORYBOARD_SCENE_BREAKDOWN,
            variables={
                "title": request.title,
                "game": request.game,
                "platform": request.platform,
                "hook": request.hook,
                "body": request.body,
                "ending": request.ending,
                "call_to_action": request.call_to_action,
                "target_duration_seconds": request.target_duration_seconds,
            },
            output_model_type=StoryboardSceneBreakdownOutput,
            execution_options=execution_options,
        )

    async def review_timing(
        self,
        request: GamingStoryboardTimingReviewRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> StoryboardTimingReviewOutput:
        """Execute the builtin storyboard timing-review prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=STORYBOARD_TIMING_REVIEW,
            variables={
                "title": request.title,
                "scene_summary": request.scene_summary,
                "target_duration_seconds": request.target_duration_seconds,
                "platform": request.platform,
            },
            output_model_type=StoryboardTimingReviewOutput,
            execution_options=execution_options,
        )

    async def generate_visual_direction(
        self,
        request: GamingStoryboardVisualDirectionRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> StoryboardVisualDirectionOutput:
        """Execute the builtin storyboard visual-direction prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=STORYBOARD_VISUAL_DIRECTION,
            variables={
                "game": request.game,
                "scene_number": request.scene_number,
                "scene_purpose": request.scene_purpose,
                "script_beat": request.script_beat,
                "visual_summary": request.visual_summary,
                "platform": request.platform,
                "duration_seconds": request.duration_seconds,
            },
            output_model_type=StoryboardVisualDirectionOutput,
            execution_options=execution_options,
        )

    async def _execute_typed(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
        output_model_type: type[TStoryboardOutput],
        execution_options: ResearchExecutionOptions | None,
    ) -> TStoryboardOutput:
        """Execute one storyboard prompt and require the expected typed parser output."""

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
                "storyboard agent received an unexpected typed output model",
                code="agent_unexpected_output_model",
                details={
                    "prompt_name": prompt_name,
                    "expected_output_model": output_model_type.__name__,
                    "actual_output_model": type(result.output).__name__,
                },
            )
        return result.output


__all__ = [
    "GamingStoryboardAgent",
    "GamingStoryboardSceneBreakdownRequest",
    "GamingStoryboardTimingReviewRequest",
    "GamingStoryboardVisualDirectionRequest",
]
