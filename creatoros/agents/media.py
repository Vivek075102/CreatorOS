"""Provider-independent media-planning agent integrations for CreatorOS."""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, field_validator

from creatoros.agents.research import ResearchExecutionOptions
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingNarrationDirectionOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingThumbnailConceptOutput,
    StoryboardSceneBreakdownOutput,
    StoryboardScenePlan,
    StoryboardVisualDirectionOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    GAMING_NARRATION_DIRECTION,
    GAMING_SCENE_MOTION_PROMPT,
    GAMING_SCENE_VISUAL_PROMPT,
    GAMING_THUMBNAIL_CONCEPT,
)
from creatoros.services import LLMExecutionRequest, LLMExecutionService

TMediaOutput = TypeVar(
    "TMediaOutput",
    GamingThumbnailConceptOutput,
    GamingSceneVisualOutput,
    GamingSceneMotionOutput,
    GamingNarrationDirectionOutput,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values for media-planning inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _build_visual_direction_summary(
    visual_direction: StoryboardVisualDirectionOutput,
) -> str:
    """Convert storyboard visual-direction guidance into one stable prompt input string."""

    return (
        f"Primary visual: {visual_direction.primary_visual}. "
        f"Composition: {visual_direction.composition}. "
        f"Motion: {visual_direction.motion}. "
        f"Style notes: {visual_direction.style_notes}. "
        f"Avoid: {visual_direction.avoid}."
    )


def _build_script_text(script_output: YouTubeShortsScriptOutput) -> str:
    """Combine the typed script sections into one narration-planning input."""

    return (
        f"{script_output.hook} "
        f"{script_output.body} "
        f"{script_output.ending} "
        f"{script_output.call_to_action}"
    )


def _build_storyboard_visual_context(
    storyboard_output: StoryboardSceneBreakdownOutput,
) -> str:
    """Convert typed storyboard output into one stable thumbnail-context string."""

    scene_descriptions = " ".join(
        (
            f"Scene {scene.scene_number}: "
            f"Purpose: {scene.purpose}. "
            f"Visual: {scene.visual}. "
            f"On-screen text: {scene.on_screen_text}."
        )
        for scene in storyboard_output.scenes
    )
    return (
        f"Storyboard title: {storyboard_output.storyboard_title}. "
        f"{scene_descriptions} "
        f"Scene count: {storyboard_output.final_scene_count}. "
        f"Estimated duration: {storyboard_output.total_estimated_duration_seconds} seconds."
    )


class GamingThumbnailConceptRequest(CreatorOSModel):
    """Normalized application input for thumbnail-concept planning."""

    title: str
    game: str
    topic: str
    angle: str
    hook: str
    platform: str
    visual_context: str

    @field_validator("title", "game", "topic", "angle", "hook", "platform", "visual_context")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_storyboard(
        cls,
        storyboard_output: StoryboardSceneBreakdownOutput,
        *,
        game: str,
        topic: str,
        angle: str,
        hook: str,
        platform: str,
    ) -> GamingThumbnailConceptRequest:
        """Build a thumbnail-concept request from typed storyboard output."""

        return cls(
            title=storyboard_output.storyboard_title,
            game=game,
            topic=topic,
            angle=angle,
            hook=hook,
            platform=platform,
            visual_context=_build_storyboard_visual_context(storyboard_output),
        )


class GamingSceneVisualPromptRequest(CreatorOSModel):
    """Normalized application input for scene-visual planning."""

    game: str
    scene_number: int = Field(gt=0)
    scene_purpose: str
    script_beat: str
    visual_direction: str
    on_screen_text: str
    platform: str

    @field_validator(
        "game",
        "scene_purpose",
        "script_beat",
        "visual_direction",
        "on_screen_text",
        "platform",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_storyboard_outputs(
        cls,
        scene_plan: StoryboardScenePlan,
        visual_direction: StoryboardVisualDirectionOutput,
        *,
        game: str,
        platform: str,
    ) -> GamingSceneVisualPromptRequest:
        """Build a scene-visual request from typed storyboard planning outputs."""

        return cls(
            game=game,
            scene_number=scene_plan.scene_number,
            scene_purpose=scene_plan.purpose,
            script_beat=scene_plan.script_beat,
            visual_direction=_build_visual_direction_summary(visual_direction),
            on_screen_text=visual_direction.on_screen_text,
            platform=platform,
        )


class GamingSceneMotionPromptRequest(CreatorOSModel):
    """Normalized application input for scene-motion planning."""

    game: str
    scene_number: int = Field(gt=0)
    scene_purpose: str
    visual_summary: str
    script_beat: str
    duration_seconds: float = Field(gt=0)
    platform: str

    @field_validator("game", "scene_purpose", "visual_summary", "script_beat", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_storyboard_scene(
        cls,
        scene_plan: StoryboardScenePlan,
        *,
        game: str,
        platform: str,
    ) -> GamingSceneMotionPromptRequest:
        """Build a scene-motion request from one typed storyboard scene plan."""

        return cls(
            game=game,
            scene_number=scene_plan.scene_number,
            scene_purpose=scene_plan.purpose,
            visual_summary=scene_plan.visual,
            script_beat=scene_plan.script_beat,
            duration_seconds=scene_plan.duration_seconds,
            platform=platform,
        )


class GamingNarrationDirectionRequest(CreatorOSModel):
    """Normalized application input for narration-direction planning."""

    title: str
    game: str
    script_text: str
    target_duration_seconds: int = Field(gt=0)
    tone: str
    platform: str

    @field_validator("title", "game", "script_text", "tone", "platform")
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
        tone: str,
        platform: str,
    ) -> GamingNarrationDirectionRequest:
        """Build a narration-direction request from one typed script output."""

        return cls(
            title=script_output.title,
            game=game,
            script_text=_build_script_text(script_output),
            target_duration_seconds=script_output.estimated_duration_seconds,
            tone=tone,
            platform=platform,
        )


class GamingMediaAgent:
    """Application media-planning agent that executes builtin media prompts through LLMExecutionService."""

    def __init__(self, llm_execution_service: LLMExecutionService) -> None:
        if not isinstance(llm_execution_service, LLMExecutionService):
            raise CreatorOSValidationError(
                "llm_execution_service must be an LLMExecutionService",
                code="agent_invalid_dependency",
                details={"dependency": "llm_execution_service"},
            )
        self.llm_execution_service = llm_execution_service

    async def generate_thumbnail_concept(
        self,
        request: GamingThumbnailConceptRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingThumbnailConceptOutput:
        """Execute the builtin thumbnail-concept prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_THUMBNAIL_CONCEPT,
            variables={
                "title": request.title,
                "game": request.game,
                "topic": request.topic,
                "angle": request.angle,
                "hook": request.hook,
                "platform": request.platform,
                "visual_context": request.visual_context,
            },
            output_model_type=GamingThumbnailConceptOutput,
            execution_options=execution_options,
        )

    async def generate_scene_visual(
        self,
        request: GamingSceneVisualPromptRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingSceneVisualOutput:
        """Execute the builtin scene-visual prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_SCENE_VISUAL_PROMPT,
            variables={
                "game": request.game,
                "scene_number": request.scene_number,
                "scene_purpose": request.scene_purpose,
                "script_beat": request.script_beat,
                "visual_direction": request.visual_direction,
                "on_screen_text": request.on_screen_text,
                "platform": request.platform,
            },
            output_model_type=GamingSceneVisualOutput,
            execution_options=execution_options,
        )

    async def generate_scene_motion(
        self,
        request: GamingSceneMotionPromptRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingSceneMotionOutput:
        """Execute the builtin scene-motion prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_SCENE_MOTION_PROMPT,
            variables={
                "game": request.game,
                "scene_number": request.scene_number,
                "scene_purpose": request.scene_purpose,
                "visual_summary": request.visual_summary,
                "script_beat": request.script_beat,
                "duration_seconds": request.duration_seconds,
                "platform": request.platform,
            },
            output_model_type=GamingSceneMotionOutput,
            execution_options=execution_options,
        )

    async def generate_narration_direction(
        self,
        request: GamingNarrationDirectionRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingNarrationDirectionOutput:
        """Execute the builtin narration-direction prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_NARRATION_DIRECTION,
            variables={
                "title": request.title,
                "game": request.game,
                "script_text": request.script_text,
                "target_duration_seconds": request.target_duration_seconds,
                "tone": request.tone,
                "platform": request.platform,
            },
            output_model_type=GamingNarrationDirectionOutput,
            execution_options=execution_options,
        )

    async def _execute_typed(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
        output_model_type: type[TMediaOutput],
        execution_options: ResearchExecutionOptions | None,
    ) -> TMediaOutput:
        """Execute one media-planning prompt and require the expected typed parser output."""

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
                "media agent received an unexpected typed output model",
                code="agent_unexpected_output_model",
                details={
                    "prompt_name": prompt_name,
                    "expected_output_model": output_model_type.__name__,
                    "actual_output_model": type(result.output).__name__,
                },
            )
        return result.output


__all__ = [
    "GamingMediaAgent",
    "GamingNarrationDirectionRequest",
    "GamingSceneMotionPromptRequest",
    "GamingSceneVisualPromptRequest",
    "GamingThumbnailConceptRequest",
]
