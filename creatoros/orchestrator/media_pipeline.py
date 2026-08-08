"""Approved media-execution pipeline for post-review CreatorOS content packages."""

from __future__ import annotations

from pydantic import ValidationError

from creatoros.core import (
    ApprovalRequiredError,
    CreatorOSError,
    CreatorOSValidationError,
    WorkflowError,
)
from creatoros.observability import get_logger
from creatoros.orchestrator.models import (
    ApprovedMediaExecutionRequest,
    GamingContentPipelineResult,
    HumanApproval,
    MediaExecutionResult,
)
from creatoros.parsing import GamingSceneMotionOutput, GamingSceneVisualOutput, StoryboardScenePlan
from creatoros.providers import ImageGenerationRequest, TTSGenerationRequest, VideoGenerationRequest
from creatoros.services import (
    MediaGenerationPackageRequest,
    MediaGenerationService,
    ShortAssemblyRequest,
    ShortAssemblyService,
)

PIPELINE_NAME = "approved_media_execution_pipeline"
STAGE_VALIDATE_REQUEST = "validate_request"
STAGE_VERIFY_PUBLICATION_READINESS = "verify_publication_readiness"
STAGE_VERIFY_HUMAN_APPROVAL = "verify_human_approval"
STAGE_BUILD_MEDIA_REQUESTS = "build_media_requests"
STAGE_MEDIA_GENERATION = "media_generation"
STAGE_SHORT_ASSEMBLY = "short_assembly"


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _build_thumbnail_prompt(result: GamingContentPipelineResult) -> str:
    """Convert the approved thumbnail concept into one deterministic image prompt."""

    thumbnail = result.media_plans.thumbnail_concept
    return (
        f"Title: {result.script.title}. "
        f"Game: {result.opportunity.game}. "
        f"Topic: {result.opportunity.topic}. "
        f"Concept: {thumbnail.concept}. "
        f"Focal subject: {thumbnail.focal_subject}. "
        f"Background: {thumbnail.background}. "
        f"Composition: {thumbnail.composition}. "
        f"Expression or action: {thumbnail.expression_or_action}. "
        f"On-image text: {thumbnail.on_image_text}. "
        f"Style direction: {thumbnail.style_direction}. "
        f"Avoid: {thumbnail.avoid}. "
        f"Evidence note: {thumbnail.evidence_note}."
    )


def _build_storyboard_scene_prompt(
    result: GamingContentPipelineResult,
    scene_plan: StoryboardScenePlan,
    scene_visual: GamingSceneVisualOutput | None,
) -> str:
    """Convert one approved scene plan into one deterministic image prompt."""

    prompt = (
        f"Title: {result.script.title}. "
        f"Game: {result.opportunity.game}. "
        f"Topic: {result.opportunity.topic}. "
        f"Scene number: {scene_plan.scene_number}. "
        f"Purpose: {scene_plan.purpose}. "
        f"Script beat: {scene_plan.script_beat}. "
        f"Visual summary: {scene_plan.visual}. "
        f"On-screen text: {scene_plan.on_screen_text}. "
        f"Duration: {scene_plan.duration_seconds} seconds."
    )
    if scene_visual is None:
        return prompt
    return (
        f"{prompt} "
        f"Subject: {scene_visual.subject}. "
        f"Environment: {scene_visual.environment}. "
        f"Action: {scene_visual.action}. "
        f"Composition: {scene_visual.composition}. "
        f"Mood: {scene_visual.mood}. "
        f"Style direction: {scene_visual.style_direction}. "
        f"Negative guidance: {scene_visual.negative_guidance}."
    )


def _build_scene_video_prompt(
    result: GamingContentPipelineResult,
    scene_plan: StoryboardScenePlan,
    scene_visual: GamingSceneVisualOutput,
    scene_motion: GamingSceneMotionOutput,
) -> str:
    """Convert approved per-scene visual and motion plans into one video prompt."""

    return (
        f"Title: {result.script.title}. "
        f"Game: {result.opportunity.game}. "
        f"Topic: {result.opportunity.topic}. "
        f"Scene number: {scene_plan.scene_number}. "
        f"Purpose: {scene_plan.purpose}. "
        f"Script beat: {scene_plan.script_beat}. "
        f"Subject: {scene_visual.subject}. "
        f"Environment: {scene_visual.environment}. "
        f"Action: {scene_visual.action}. "
        f"Composition: {scene_visual.composition}. "
        f"Mood: {scene_visual.mood}. "
        f"On-screen text: {scene_visual.on_screen_text}. "
        f"Style direction: {scene_visual.style_direction}. "
        f"Negative guidance: {scene_visual.negative_guidance}. "
        f"Primary motion: {scene_motion.primary_motion}. "
        f"Subject movement: {scene_motion.subject_movement}. "
        f"Camera direction: {scene_motion.camera_direction}. "
        f"Transition guidance: {scene_motion.transition_guidance}. "
        f"Pacing: {scene_motion.pacing}. "
        f"Avoid: {scene_motion.avoid}."
    )


class MediaExecutionPipeline:
    """Execute approved media generation and final Short assembly after planning stops."""

    def __init__(
        self,
        *,
        media_generation_service: MediaGenerationService,
        short_assembly_service: ShortAssemblyService,
    ) -> None:
        self.media_generation_service = self._validate_dependency(
            media_generation_service,
            MediaGenerationService,
            dependency_name="media_generation_service",
        )
        self.short_assembly_service = self._validate_dependency(
            short_assembly_service,
            ShortAssemblyService,
            dependency_name="short_assembly_service",
        )
        self.logger = get_logger("orchestrator.media_pipeline")

    def build_media_generation_request(
        self,
        request: ApprovedMediaExecutionRequest,
    ) -> MediaGenerationPackageRequest:
        """Convert approved typed planning outputs into provider-neutral media requests."""

        self._verify_publication_readiness(request.content_result)
        self._verify_human_approval(request.approval)

        scene_visuals = self._build_aligned_scene_visuals(request.content_result)
        scene_motions = self._build_aligned_scene_motions(request.content_result)

        scene_image_requests = tuple(
            ImageGenerationRequest(
                prompt=_build_storyboard_scene_prompt(
                    request.content_result,
                    scene_plan,
                    scene_visuals[index] if scene_visuals else None,
                )
            )
            for index, scene_plan in enumerate(request.content_result.storyboard.scenes)
        )

        scene_video_requests: tuple[VideoGenerationRequest, ...] = ()
        if scene_visuals and scene_motions:
            scene_video_requests = tuple(
                VideoGenerationRequest(
                    prompt=_build_scene_video_prompt(
                        request.content_result,
                        scene_plan,
                        scene_visuals[index],
                        scene_motions[index],
                    ),
                    duration_seconds=scene_plan.duration_seconds,
                )
                for index, scene_plan in enumerate(request.content_result.storyboard.scenes)
            )

        try:
            return MediaGenerationPackageRequest(
                thumbnail_request=ImageGenerationRequest(
                    prompt=_build_thumbnail_prompt(request.content_result)
                ),
                narration_request=TTSGenerationRequest(
                    text=request.content_result.media_plans.narration_direction.narration_text,
                ),
                scene_image_requests=scene_image_requests,
                scene_video_requests=scene_video_requests,
                provider_selection=request.provider_selection,
            )
        except ValidationError as error:
            raise CreatorOSValidationError(
                "approved media request could not be mapped into media generation inputs",
                code="media_execution_mapping_invalid",
            ) from error

    async def execute(
        self,
        request: ApprovedMediaExecutionRequest,
    ) -> MediaExecutionResult:
        """Execute the post-approval media pipeline through generation and assembly."""

        active_stage = STAGE_VALIDATE_REQUEST
        self.logger.info("media_execution_started", pipeline_name=PIPELINE_NAME)

        try:
            active_stage = STAGE_VERIFY_PUBLICATION_READINESS
            self._verify_publication_readiness(request.content_result)

            active_stage = STAGE_VERIFY_HUMAN_APPROVAL
            self._verify_human_approval(request.approval)

            active_stage = STAGE_BUILD_MEDIA_REQUESTS
            media_generation_request = self.build_media_generation_request(request)

            active_stage = STAGE_MEDIA_GENERATION
            generated_media = await self.media_generation_service.generate_package(
                media_generation_request
            )

            active_stage = STAGE_SHORT_ASSEMBLY
            assembly = await self.short_assembly_service.assemble(
                ShortAssemblyRequest(
                    storyboard=request.content_result.storyboard,
                    generated_media=generated_media,
                ),
                render_provider_name=request.render_provider_name,
            )
        except CreatorOSError:
            self.logger.exception(
                "media_execution_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
            )
            raise
        except Exception as error:
            self.logger.exception(
                "media_execution_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
            )
            raise WorkflowError(
                "approved media execution pipeline failed",
                code="approved_media_execution_pipeline_failed",
                details={"stage": active_stage},
            ) from error

        result = MediaExecutionResult(
            content_result=request.content_result,
            approval=request.approval,
            generated_media=generated_media,
            assembly=assembly,
        )
        self.logger.info(
            "media_execution_completed",
            pipeline_name=PIPELINE_NAME,
            success=True,
            scene_count=result.assembly.scene_count,
        )
        return result

    def _verify_publication_readiness(self, result: GamingContentPipelineResult) -> None:
        """Require positive publication readiness before any media work begins."""

        if result.publication_readiness.decision != "ready_for_human_review":
            raise WorkflowError(
                "content result is not publication-ready for media execution",
                code="media_execution_not_publication_ready",
                details={"decision": result.publication_readiness.decision},
            )

    def _verify_human_approval(self, approval: HumanApproval) -> None:
        """Require explicit positive human approval before any media work begins."""

        if not approval.approved:
            raise ApprovalRequiredError(
                "explicit human approval is required before media execution",
                code="media_execution_approval_required",
                details={"approved": approval.approved},
            )

    def _build_aligned_scene_visuals(
        self,
        result: GamingContentPipelineResult,
    ) -> tuple[GamingSceneVisualOutput, ...]:
        """Validate and return aligned optional scene-visual plans."""

        scene_visuals = result.media_plans.scene_visuals
        if not scene_visuals:
            return ()

        if len(scene_visuals) != len(result.storyboard.scenes):
            raise CreatorOSValidationError(
                "scene_visuals must match storyboard scene count when supplied",
                code="media_execution_scene_visual_count_mismatch",
                details={
                    "storyboard_scene_count": len(result.storyboard.scenes),
                    "scene_visual_count": len(scene_visuals),
                },
            )

        for expected_scene_number, scene_visual in enumerate(scene_visuals, start=1):
            if scene_visual.scene_number != expected_scene_number:
                raise CreatorOSValidationError(
                    "scene_visuals must remain sequential starting at 1",
                    code="media_execution_scene_visual_order_invalid",
                    details={
                        "expected_scene_number": expected_scene_number,
                        "actual_scene_number": scene_visual.scene_number,
                    },
                )
        return scene_visuals

    def _build_aligned_scene_motions(
        self,
        result: GamingContentPipelineResult,
    ) -> tuple[GamingSceneMotionOutput, ...]:
        """Validate and return aligned optional scene-motion plans."""

        scene_motions = result.media_plans.scene_motions
        if not scene_motions:
            return ()

        if len(scene_motions) != len(result.storyboard.scenes):
            raise CreatorOSValidationError(
                "scene_motions must match storyboard scene count when supplied",
                code="media_execution_scene_motion_count_mismatch",
                details={
                    "storyboard_scene_count": len(result.storyboard.scenes),
                    "scene_motion_count": len(scene_motions),
                },
            )

        for expected_scene_number, scene_motion in enumerate(scene_motions, start=1):
            storyboard_scene = result.storyboard.scenes[expected_scene_number - 1]
            if scene_motion.scene_number != expected_scene_number:
                raise CreatorOSValidationError(
                    "scene_motions must remain sequential starting at 1",
                    code="media_execution_scene_motion_order_invalid",
                    details={
                        "expected_scene_number": expected_scene_number,
                        "actual_scene_number": scene_motion.scene_number,
                    },
                )
            if scene_motion.duration_seconds != storyboard_scene.duration_seconds:
                raise CreatorOSValidationError(
                    "scene motion duration must match storyboard duration",
                    code="media_execution_scene_motion_duration_mismatch",
                    details={
                        "scene_number": expected_scene_number,
                        "storyboard_duration_seconds": storyboard_scene.duration_seconds,
                        "scene_motion_duration_seconds": scene_motion.duration_seconds,
                    },
                )
        return scene_motions

    @staticmethod
    def _validate_dependency[TDependency](
        dependency: object,
        dependency_type: type[TDependency],
        *,
        dependency_name: str,
    ) -> TDependency:
        """Validate one required pipeline dependency safely."""

        if not isinstance(dependency, dependency_type):
            raise CreatorOSValidationError(
                f"{dependency_name} must be a {dependency_type.__name__}",
                code="pipeline_invalid_dependency",
                details={"dependency": dependency_name},
            )
        return dependency


def create_media_execution_pipeline(
    *,
    media_generation_service: MediaGenerationService | None = None,
    short_assembly_service: ShortAssemblyService | None = None,
    settings=None,
) -> MediaExecutionPipeline:
    """Create a safe mock-first approved media-execution pipeline."""

    from creatoros.services import create_media_generation_service, create_short_assembly_service

    resolved_media_generation_service = (
        create_media_generation_service(settings=settings)
        if media_generation_service is None
        else media_generation_service
    )
    resolved_short_assembly_service = (
        create_short_assembly_service(settings=settings)
        if short_assembly_service is None
        else short_assembly_service
    )
    return MediaExecutionPipeline(
        media_generation_service=resolved_media_generation_service,
        short_assembly_service=resolved_short_assembly_service,
    )


__all__ = [
    "PIPELINE_NAME",
    "STAGE_BUILD_MEDIA_REQUESTS",
    "STAGE_MEDIA_GENERATION",
    "STAGE_SHORT_ASSEMBLY",
    "STAGE_VALIDATE_REQUEST",
    "STAGE_VERIFY_HUMAN_APPROVAL",
    "STAGE_VERIFY_PUBLICATION_READINESS",
    "MediaExecutionPipeline",
    "create_media_execution_pipeline",
]
