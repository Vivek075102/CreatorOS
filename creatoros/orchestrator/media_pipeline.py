"""Approved media-execution pipeline for post-review CreatorOS content packages."""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from creatoros.core import (
    ApprovalRequiredError,
    ArtifactAlreadyExistsError,
    ConfigurationError,
    CreatorOSError,
    CreatorOSValidationError,
    WorkflowError,
)
from creatoros.domain import AssetType, GeneratedAsset, HostedAsset
from creatoros.observability import get_logger
from creatoros.orchestrator.models import (
    ApprovedMediaExecutionRequest,
    GamingContentPipelineResult,
    HumanApproval,
    MediaExecutionResult,
    ProductionExecutionPlan,
)
from creatoros.parsing import GamingSceneMotionOutput, GamingSceneVisualOutput, StoryboardScenePlan
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    TTSGenerationRequest,
    VideoGenerationRequest,
)
from creatoros.providers.openai.tts import SUPPORTED_OPENAI_TTS_VOICES
from creatoros.services import (
    ArtifactMaterializationService,
    AssetHostingService,
    GeneratedMediaPackage,
    MaterializedMediaPackage,
    MediaGenerationPackageRequest,
    MediaGenerationService,
    MediaProviderSelection,
    ShortAssemblyRequest,
    ShortAssemblyService,
)

PIPELINE_NAME = "approved_media_execution_pipeline"
STAGE_VALIDATE_REQUEST = "validate_request"
STAGE_PREFLIGHT = "preflight"
STAGE_VERIFY_PUBLICATION_READINESS = "verify_publication_readiness"
STAGE_VERIFY_HUMAN_APPROVAL = "verify_human_approval"
STAGE_BUILD_MEDIA_REQUESTS = "build_media_requests"
STAGE_VERIFY_LIVE_CALL_POLICY = "verify_live_call_policy"
STAGE_MEDIA_GENERATION = "media_generation"
STAGE_ASSET_HOSTING = "asset_hosting"
STAGE_ARTIFACT_MATERIALIZATION = "artifact_materialization"
STAGE_BUILD_ASSEMBLY_INPUTS = "build_assembly_inputs"
STAGE_SHORT_ASSEMBLY = "short_assembly"
STAGE_RESULT_VALIDATION = "result_validation"

SUPPORTED_OUTPUT_FORMATS = frozenset({"mp4"})
PROTECTED_FINAL_OUTPUT_FILENAME = "final_short.mp4"


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_text(value: object) -> str | None:
    """Normalize optional text-like values to stripped strings or ``None``."""

    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
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


def _is_mock_provider_name(value: str | None) -> bool:
    """Return whether a provider name represents the deterministic mock path."""

    if value is None:
        return False
    return value.strip().casefold() == "mock"


def _is_live_provider_name(value: str | None) -> bool:
    """Return whether a provider name represents a non-mock live path."""

    return not _is_mock_provider_name(value)


def _normalize_output_format(value: str) -> str:
    """Normalize a symbolic output format for explicit validation."""

    return _validate_non_blank(value.lower(), field_name="output_format")


def _failure_category_for_stage(stage: str) -> str:
    """Map one internal stage name to a safe public failure category."""

    if stage == STAGE_PREFLIGHT:
        return "preflight_failed"
    if stage == STAGE_MEDIA_GENERATION:
        return "media_generation_failed"
    if stage == STAGE_ASSET_HOSTING:
        return "asset_hosting_failed"
    if stage == STAGE_ARTIFACT_MATERIALIZATION:
        return "materialization_failed"
    if stage == STAGE_BUILD_ASSEMBLY_INPUTS:
        return "assembly_failed"
    if stage in {STAGE_SHORT_ASSEMBLY, STAGE_RESULT_VALIDATION}:
        return "render_failed"
    return "workflow_failed"


def _materialize_generated_media_for_assembly(
    generated_media: GeneratedMediaPackage,
    materialized_media: MaterializedMediaPackage,
) -> GeneratedMediaPackage:
    """Rebuild generated-media contracts so assembly uses local materialized artifact URIs."""

    if (generated_media.thumbnail is None) != (materialized_media.thumbnail is None):
        raise CreatorOSValidationError(
            "thumbnail materialization did not match generated media",
            code="media_execution_materialization_mismatch",
            details={"asset_name": "thumbnail"},
        )
    if (generated_media.narration is None) != (materialized_media.narration is None):
        raise CreatorOSValidationError(
            "narration materialization did not match generated media",
            code="media_execution_materialization_mismatch",
            details={"asset_name": "narration"},
        )
    if len(generated_media.scene_images) != len(materialized_media.scene_images):
        raise CreatorOSValidationError(
            "scene image materialization count did not match generated media",
            code="media_execution_materialization_mismatch",
            details={"asset_name": "scene_images"},
        )
    if len(generated_media.scene_videos) != len(materialized_media.scene_videos):
        raise CreatorOSValidationError(
            "scene video materialization count did not match generated media",
            code="media_execution_materialization_mismatch",
            details={"asset_name": "scene_videos"},
        )

    def _with_local_artifact(
        media: GeneratedImage | GeneratedAudio | GeneratedVideo,
        path: str,
    ) -> GeneratedImage | GeneratedAudio | GeneratedVideo:
        return cast(
            GeneratedImage | GeneratedAudio | GeneratedVideo,
            media.model_copy(
                update={
                    "artifact": media.artifact.model_copy(
                        update={
                            "uri": path,
                            "metadata": {
                                **dict(media.artifact.metadata),
                                "local": True,
                                "workspace_run_id": materialized_media.workspace.run_id,
                            },
                        }
                    ),
                    "payload_bytes": None,
                    "metadata": {
                        **dict(media.metadata),
                        "local": True,
                        "materialized_path": path,
                        "workspace_run_id": materialized_media.workspace.run_id,
                    },
                }
            ),
        )

    thumbnail = None
    if generated_media.thumbnail is not None and materialized_media.thumbnail is not None:
        thumbnail = cast(
            GeneratedImage,
            _with_local_artifact(
                generated_media.thumbnail,
                str(materialized_media.thumbnail.path),
            ),
        )

    narration = None
    if generated_media.narration is not None and materialized_media.narration is not None:
        narration = cast(
            GeneratedAudio,
            _with_local_artifact(
                generated_media.narration,
                str(materialized_media.narration.path),
            ),
        )

    scene_images = tuple(
        cast(GeneratedImage, _with_local_artifact(image, str(materialized.path)))
        for image, materialized in zip(
            generated_media.scene_images,
            materialized_media.scene_images,
            strict=True,
        )
    )
    scene_videos = tuple(
        cast(GeneratedVideo, _with_local_artifact(video, str(materialized.path)))
        for video, materialized in zip(
            generated_media.scene_videos,
            materialized_media.scene_videos,
            strict=True,
        )
    )

    return GeneratedMediaPackage(
        thumbnail=thumbnail,
        narration=narration,
        scene_images=scene_images,
        scene_videos=scene_videos,
    )


def _build_hosted_reference_asset(hosted_asset: HostedAsset) -> GeneratedAsset:
    """Convert one hosted asset into the provider-neutral reference-image contract."""

    return GeneratedAsset(
        asset_type=AssetType.IMAGE,
        uri=hosted_asset.public_url,
        metadata={
            "hosted": True,
            "hosting_provider_name": hosted_asset.provider_name,
            "provider_asset_id": hosted_asset.provider_asset_id,
            "source_asset_id": hosted_asset.source_asset.id,
        },
    )


class MediaExecutionPipeline:
    """Execute approved media generation and final Short assembly after planning stops."""

    def __init__(
        self,
        *,
        media_generation_service: MediaGenerationService,
        asset_hosting_service: AssetHostingService,
        artifact_materialization_service: ArtifactMaterializationService,
        short_assembly_service: ShortAssemblyService,
    ) -> None:
        self.media_generation_service = self._validate_dependency(
            media_generation_service,
            MediaGenerationService,
            dependency_name="media_generation_service",
        )
        self.asset_hosting_service = self._validate_dependency(
            asset_hosting_service,
            AssetHostingService,
            dependency_name="asset_hosting_service",
        )
        self.artifact_materialization_service = self._validate_dependency(
            artifact_materialization_service,
            ArtifactMaterializationService,
            dependency_name="artifact_materialization_service",
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
        narration_direction = request.content_result.media_plans.narration_direction
        narration_voice = self._resolve_narration_voice(
            narration_direction=narration_direction,
        )

        scene_visuals = self._build_aligned_scene_visuals(request.content_result)

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

        try:
            return MediaGenerationPackageRequest(
                thumbnail_request=ImageGenerationRequest(
                    prompt=_build_thumbnail_prompt(request.content_result)
                ),
                narration_request=TTSGenerationRequest(
                    text=narration_direction.narration_text,
                    voice=narration_voice,
                ),
                scene_image_requests=scene_image_requests,
                provider_selection=request.provider_selection,
            )
        except ValidationError as error:
            raise CreatorOSValidationError(
                "approved media request could not be mapped into media generation inputs",
                code="media_execution_mapping_invalid",
            ) from error

    def build_execution_plan(
        self,
        request: ApprovedMediaExecutionRequest,
    ) -> ProductionExecutionPlan:
        """Build one deterministic production execution plan without generating media."""

        plan, _ = self._run_preflight(request, require_live_confirmation=False)
        return plan

    async def execute(
        self,
        request: ApprovedMediaExecutionRequest,
    ) -> MediaExecutionResult:
        """Execute the post-approval media pipeline through generation and assembly."""

        active_stage = STAGE_VALIDATE_REQUEST
        self.logger.info("media_execution_started", pipeline_name=PIPELINE_NAME)

        try:
            active_stage = STAGE_PREFLIGHT
            plan, media_generation_request = self._run_preflight(
                request,
                require_live_confirmation=True,
            )

            active_stage = STAGE_MEDIA_GENERATION
            generated_media = await self.media_generation_service.generate_package(
                media_generation_request
            )
            if plan.video_generation_count > 0:
                active_stage = STAGE_ASSET_HOSTING
                hosted_scene_images = await self._host_scene_images_for_video_generation(
                    generated_media=generated_media,
                    request=request,
                )
                active_stage = STAGE_MEDIA_GENERATION
                generated_scene_videos = await self._generate_scene_videos_from_hosted_images(
                    content_result=request.content_result,
                    hosted_scene_images=hosted_scene_images,
                    provider_selection=request.provider_selection,
                )
                generated_media = generated_media.model_copy(
                    update={"scene_videos": generated_scene_videos}
                )
            self.logger.info(
                "media_execution_stage_completed",
                pipeline_name=PIPELINE_NAME,
                stage=STAGE_MEDIA_GENERATION,
                run_id=request.run_id,
                success=True,
            )

            active_stage = STAGE_ARTIFACT_MATERIALIZATION
            materialized_media = self.artifact_materialization_service.materialize_package(
                generated_media,
                run_id=request.run_id,
            )
            self.logger.info(
                "media_execution_stage_completed",
                pipeline_name=PIPELINE_NAME,
                stage=STAGE_ARTIFACT_MATERIALIZATION,
                run_id=request.run_id,
                success=True,
            )

            active_stage = STAGE_BUILD_ASSEMBLY_INPUTS
            assembly_media = _materialize_generated_media_for_assembly(
                generated_media,
                materialized_media,
            )

            active_stage = STAGE_SHORT_ASSEMBLY
            assembly = await self.short_assembly_service.assemble(
                ShortAssemblyRequest(
                    storyboard=request.content_result.storyboard,
                    generated_media=assembly_media,
                    width=request.width,
                    height=request.height,
                    fps=request.fps,
                    output_format=request.output_format,
                ),
                render_provider_name=request.render_provider_name,
            )
            self.logger.info(
                "media_execution_stage_completed",
                pipeline_name=PIPELINE_NAME,
                stage=STAGE_SHORT_ASSEMBLY,
                run_id=request.run_id,
                success=True,
            )

            active_stage = STAGE_RESULT_VALIDATION
            result = MediaExecutionResult(
                run_id=request.run_id,
                content_result=request.content_result,
                approval=request.approval,
                provider_selection=request.provider_selection,
                render_provider_name=request.render_provider_name,
                generated_media=generated_media,
                materialized_media=materialized_media,
                assembly=assembly,
            )
            self._validate_result_integrity(result, request=request)
        except CreatorOSError as error:
            error.details.setdefault("stage", active_stage)
            error.details.setdefault(
                "failure_category",
                _failure_category_for_stage(active_stage),
            )
            self.logger.exception(
                "media_execution_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
                failure_category=error.details["failure_category"],
            )
            raise
        except Exception as error:
            failure_category = _failure_category_for_stage(active_stage)
            self.logger.exception(
                "media_execution_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
                failure_category=failure_category,
            )
            raise WorkflowError(
                "approved media execution pipeline failed",
                code="approved_media_execution_pipeline_failed",
                details={
                    "stage": active_stage,
                    "failure_category": failure_category,
                },
            ) from error

        self.logger.info(
            "media_execution_completed",
            pipeline_name=PIPELINE_NAME,
            run_id=request.run_id,
            success=True,
            scene_count=plan.scene_count,
        )
        return result

    async def _host_scene_images_for_video_generation(
        self,
        *,
        generated_media: GeneratedMediaPackage,
        request: ApprovedMediaExecutionRequest,
    ) -> tuple[HostedAsset, ...]:
        """Host local scene images so video providers can consume remote-safe references."""

        selection = (
            MediaProviderSelection()
            if request.provider_selection is None
            else request.provider_selection
        )
        hosted_assets: list[HostedAsset] = []
        try:
            for scene_image in generated_media.scene_images:
                hosted_assets.append(
                    await self.asset_hosting_service.host_asset(
                        scene_image.artifact,
                        provider_name=selection.hosting_provider_name,
                    )
                )
            self.logger.info(
                "media_execution_stage_completed",
                pipeline_name=PIPELINE_NAME,
                stage=STAGE_ASSET_HOSTING,
                run_id=request.run_id,
                hosted_asset_count=len(hosted_assets),
                success=True,
            )
            return tuple(hosted_assets)
        except Exception:
            await self._cleanup_hosted_scene_images(
                hosted_scene_images=tuple(hosted_assets),
                provider_selection=request.provider_selection,
            )
            raise

    async def _generate_scene_videos_from_hosted_images(
        self,
        *,
        content_result: GamingContentPipelineResult,
        hosted_scene_images: tuple[HostedAsset, ...],
        provider_selection: MediaProviderSelection | None,
    ) -> tuple[GeneratedVideo, ...]:
        """Generate scene videos only after remote-safe hosted image references exist."""

        video_requests = self._build_scene_video_requests(
            content_result=content_result,
            hosted_scene_images=hosted_scene_images,
        )
        selection = (
            MediaProviderSelection()
            if provider_selection is None
            else provider_selection
        )
        generated_videos: list[GeneratedVideo] = []
        try:
            for video_request in video_requests:
                generated_videos.append(
                    await self.media_generation_service.generate_video(
                        video_request,
                        provider_name=selection.video_provider_name,
                    )
                )
            return tuple(generated_videos)
        finally:
            await self._cleanup_hosted_scene_images(
                hosted_scene_images=hosted_scene_images,
                provider_selection=provider_selection,
            )

    def _run_preflight(
        self,
        request: ApprovedMediaExecutionRequest,
        *,
        require_live_confirmation: bool,
    ) -> tuple[ProductionExecutionPlan, MediaGenerationPackageRequest]:
        """Validate a production request fully before any media provider call occurs."""

        self.logger.info(
            "production_preflight_started",
            pipeline_name=PIPELINE_NAME,
            run_id=request.run_id,
        )

        self._validate_request_fields(request)
        self._verify_publication_readiness(request.content_result)
        self._verify_human_approval(request.approval)
        media_generation_request = self.build_media_generation_request(request)

        (
            effective_image_provider,
            effective_tts_provider,
            effective_video_provider,
            effective_hosting_provider,
            effective_render_provider,
        ) = self._resolve_effective_provider_names(request)
        plan = self._build_execution_plan(
            request=request,
            media_request=media_generation_request,
            image_provider=effective_image_provider,
            tts_provider=effective_tts_provider,
            video_provider=effective_video_provider,
            hosting_provider=effective_hosting_provider,
            render_provider=effective_render_provider,
        )

        if require_live_confirmation:
            self._verify_live_call_policy(request, media_generation_request)
        self._validate_registered_providers(
            media_request=media_generation_request,
            scene_video_generation_count=plan.video_generation_count,
            image_provider=effective_image_provider,
            tts_provider=effective_tts_provider,
            video_provider=effective_video_provider,
            hosting_provider=effective_hosting_provider,
            render_provider=effective_render_provider,
        )
        self._validate_live_provider_configuration(plan, media_request=media_generation_request)
        self._validate_workspace_integrity(request)
        self._validate_assembly_preflight(request, media_generation_request)

        self.logger.info(
            "production_preflight_completed",
            pipeline_name=PIPELINE_NAME,
            run_id=plan.run_id,
            scene_count=plan.scene_count,
            image_generation_count=plan.image_generation_count,
            tts_generation_count=plan.tts_generation_count,
            video_generation_count=plan.video_generation_count,
            uses_live_media=plan.will_use_live_media,
            render_provider=plan.render_provider,
            success=True,
        )
        self.logger.info(
            "production_plan_created",
            pipeline_name=PIPELINE_NAME,
            run_id=plan.run_id,
            scene_count=plan.scene_count,
            image_generation_count=plan.image_generation_count,
            tts_generation_count=plan.tts_generation_count,
            video_generation_count=plan.video_generation_count,
            uses_live_media=plan.will_use_live_media,
            render_provider=plan.render_provider,
        )
        return plan, media_generation_request

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

    def _verify_live_call_policy(
        self,
        request: ApprovedMediaExecutionRequest,
        media_request: MediaGenerationPackageRequest,
    ) -> None:
        """Require explicit confirmation before any non-mock media provider can be used."""

        selection = (
            MediaProviderSelection()
            if request.provider_selection is None
            else request.provider_selection
        )
        defaults = self.media_generation_service.settings
        effective_image_provider = (
            defaults.default_image_provider
            if selection.image_provider_name is None
            else selection.image_provider_name
        )
        effective_tts_provider = (
            defaults.default_tts_provider
            if selection.tts_provider_name is None
            else selection.tts_provider_name
        )
        effective_video_provider = (
            defaults.default_video_provider
            if selection.video_provider_name is None
            else selection.video_provider_name
        )
        effective_hosting_provider = (
            defaults.default_asset_hosting_provider
            if selection.hosting_provider_name is None
            else selection.hosting_provider_name
        )
        scene_video_generation_count = self._count_scene_video_requests(request.content_result)

        live_media_providers: list[str] = []
        if (
            (media_request.thumbnail_request is not None or media_request.scene_image_requests)
            and not _is_mock_provider_name(effective_image_provider)
        ):
            live_media_providers.append(effective_image_provider)
        if media_request.narration_request is not None and not _is_mock_provider_name(effective_tts_provider):
            live_media_providers.append(effective_tts_provider)
        if scene_video_generation_count > 0 and not _is_mock_provider_name(effective_hosting_provider):
            live_media_providers.append(effective_hosting_provider)
        if scene_video_generation_count > 0 and not _is_mock_provider_name(effective_video_provider):
            live_media_providers.append(effective_video_provider)

        if live_media_providers and not request.confirm_live_media_calls:
            raise ApprovalRequiredError(
                "explicit live media confirmation is required before non-mock media generation",
                code="media_execution_live_confirmation_required",
                details={"provider_names": tuple(dict.fromkeys(live_media_providers))},
            )

    def _resolve_effective_provider_names(
        self,
        request: ApprovedMediaExecutionRequest,
    ) -> tuple[str, str, str, str, str]:
        """Resolve the effective provider names used for plan and preflight validation."""

        selection = (
            MediaProviderSelection()
            if request.provider_selection is None
            else request.provider_selection
        )
        settings = self.media_generation_service.settings
        image_provider = (
            settings.default_image_provider
            if selection.image_provider_name is None
            else selection.image_provider_name
        )
        tts_provider = (
            settings.default_tts_provider
            if selection.tts_provider_name is None
            else selection.tts_provider_name
        )
        video_provider = (
            settings.default_video_provider
            if selection.video_provider_name is None
            else selection.video_provider_name
        )
        hosting_provider = (
            settings.default_asset_hosting_provider
            if selection.hosting_provider_name is None
            else selection.hosting_provider_name
        )
        render_provider = (
            self.short_assembly_service.media_render_service.settings.default_render_provider
            if request.render_provider_name is None
            else request.render_provider_name
        )
        return image_provider, tts_provider, video_provider, hosting_provider, render_provider

    def _build_execution_plan(
        self,
        *,
        request: ApprovedMediaExecutionRequest,
        media_request: MediaGenerationPackageRequest,
        image_provider: str,
        tts_provider: str,
        video_provider: str,
        hosting_provider: str,
        render_provider: str,
    ) -> ProductionExecutionPlan:
        """Summarize one approved production request without exposing prompts or content bodies."""

        scene_video_generation_count = self._count_scene_video_requests(request.content_result)
        image_generation_count = (
            (1 if media_request.thumbnail_request is not None else 0)
            + len(media_request.scene_image_requests)
        )
        tts_generation_count = 1 if media_request.narration_request is not None else 0
        video_generation_count = scene_video_generation_count
        asset_hosting_calls = scene_video_generation_count
        live_media_call_count = 0
        if _is_live_provider_name(image_provider):
            live_media_call_count += image_generation_count
        if _is_live_provider_name(tts_provider):
            live_media_call_count += tts_generation_count
        if asset_hosting_calls > 0 and _is_live_provider_name(hosting_provider):
            live_media_call_count += asset_hosting_calls
        if _is_live_provider_name(video_provider):
            live_media_call_count += video_generation_count

        workspace = self.artifact_materialization_service.create_workspace(run_id=request.run_id)
        return ProductionExecutionPlan(
            run_id=request.run_id,
            approved=request.approval.approved,
            image_provider=image_provider,
            tts_provider=tts_provider,
            video_provider=video_provider,
            hosting_provider=hosting_provider,
            render_provider=render_provider,
            scene_count=len(request.content_result.storyboard.scenes),
            image_generation_count=image_generation_count,
            tts_generation_count=tts_generation_count,
            video_generation_count=video_generation_count,
            asset_hosting_calls=asset_hosting_calls,
            live_media_call_count=live_media_call_count,
            will_use_live_media=live_media_call_count > 0,
            final_width=request.width,
            final_height=request.height,
            fps=request.fps,
            output_format=_normalize_output_format(request.output_format),
            workspace_path=str(workspace.workspace_path),
            execution_started=False,
        )

    def _validate_request_fields(self, request: ApprovedMediaExecutionRequest) -> None:
        """Validate request fields explicitly so preflight catches unsafe constructed models."""

        from creatoros.services.artifact_materialization import ArtifactWorkspace

        ArtifactWorkspace.validate_run_id(request.run_id)
        if request.width <= 0:
            raise CreatorOSValidationError(
                "width must be greater than zero",
                code="media_execution_invalid_dimensions",
                details={"field": "width"},
            )
        if request.height <= 0:
            raise CreatorOSValidationError(
                "height must be greater than zero",
                code="media_execution_invalid_dimensions",
                details={"field": "height"},
            )
        if not math.isfinite(request.fps) or request.fps <= 0:
            raise CreatorOSValidationError(
                "fps must be a positive finite value",
                code="media_execution_invalid_fps",
                details={"field": "fps"},
            )
        output_format = _normalize_output_format(request.output_format)
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise CreatorOSValidationError(
                "output_format is not supported",
                code="media_execution_output_format_unsupported",
                details={"output_format": output_format},
            )

    def _validate_registered_providers(
        self,
        *,
        media_request: MediaGenerationPackageRequest,
        scene_video_generation_count: int,
        image_provider: str,
        tts_provider: str,
        video_provider: str,
        hosting_provider: str,
        render_provider: str,
    ) -> None:
        """Validate that every effective provider can be resolved before execution begins."""

        if media_request.thumbnail_request is not None or media_request.scene_image_requests:
            self.media_generation_service._resolve_image_provider(image_provider)
        if media_request.narration_request is not None:
            self.media_generation_service._resolve_tts_provider(tts_provider)
        if scene_video_generation_count > 0:
            self.asset_hosting_service._resolve_provider(hosting_provider)
            self.media_generation_service._resolve_video_provider(video_provider)
        self.short_assembly_service.media_render_service._resolve_provider(render_provider)

    def _validate_live_provider_configuration(
        self,
        plan: ProductionExecutionPlan,
        *,
        media_request: MediaGenerationPackageRequest,
    ) -> None:
        """Validate configuration required for explicit live providers without any network calls."""

        settings = self.media_generation_service.settings
        if plan.image_generation_count > 0 and plan.image_provider == "openai-image":
            if settings.openai_api_key is None or not settings.openai_api_key.strip():
                raise ConfigurationError(
                    "OPENAI_API_KEY is required for live image generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.image_provider, "field": "openai_api_key"},
                )
            if settings.default_image_model is None or not settings.default_image_model.strip():
                raise ConfigurationError(
                    "DEFAULT_IMAGE_MODEL is required for live image generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.image_provider, "field": "default_image_model"},
                )
        if plan.tts_generation_count > 0 and plan.tts_provider == "openai-tts":
            if settings.openai_api_key is None or not settings.openai_api_key.strip():
                raise ConfigurationError(
                    "OPENAI_API_KEY is required for live narration generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.tts_provider, "field": "openai_api_key"},
                )
            if settings.default_tts_model is None or not settings.default_tts_model.strip():
                raise ConfigurationError(
                    "DEFAULT_TTS_MODEL is required for live narration generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.tts_provider, "field": "default_tts_model"},
                )
            narration_request = media_request.narration_request
            voice = None if narration_request is None else _normalize_optional_text(narration_request.voice)
            if voice is None:
                raise ConfigurationError(
                    "DEFAULT_TTS_VOICE is required for live narration generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.tts_provider, "field": "default_tts_voice"},
                )
            normalized_voice = voice.lower()
            if normalized_voice not in SUPPORTED_OPENAI_TTS_VOICES:
                raise CreatorOSValidationError(
                    "voice is not supported by the OpenAI TTS adapter",
                    code="media_execution_invalid_voice",
                    details={
                        "provider_name": plan.tts_provider,
                        "field": "voice",
                        "supported_voices": sorted(SUPPORTED_OPENAI_TTS_VOICES),
                    },
                )
        if plan.asset_hosting_calls > 0 and plan.hosting_provider == "cloudinary":
            required_cloudinary_fields = (
                ("cloudinary_cloud_name", settings.cloudinary_cloud_name),
                ("cloudinary_api_key", settings.cloudinary_api_key),
                ("cloudinary_api_secret", settings.cloudinary_api_secret),
            )
            for field_name, value in required_cloudinary_fields:
                if value is None or not value.strip():
                    raise ConfigurationError(
                        "Cloudinary configuration is required for hosted scene-image references",
                        code="media_execution_missing_live_configuration",
                        details={"provider_name": plan.hosting_provider, "field": field_name},
                    )
        if plan.video_generation_count > 0 and plan.video_provider == "kling":
            if settings.kling_api_key is None or not settings.kling_api_key.strip():
                raise ConfigurationError(
                    "KLING_API_KEY is required for live scene video generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.video_provider, "field": "kling_api_key"},
                )
            if settings.default_video_model is None or not settings.default_video_model.strip():
                raise ConfigurationError(
                    "DEFAULT_VIDEO_MODEL is required for live scene video generation",
                    code="media_execution_missing_live_configuration",
                    details={"provider_name": plan.video_provider, "field": "default_video_model"},
                )

    def _count_scene_video_requests(
        self,
        result: GamingContentPipelineResult,
    ) -> int:
        """Return the number of scene videos planned for one approved content package."""

        scene_visuals = self._build_aligned_scene_visuals(result)
        scene_motions = self._build_aligned_scene_motions(result)
        if not scene_visuals or not scene_motions:
            return 0
        return len(result.storyboard.scenes)

    def _build_scene_video_requests(
        self,
        *,
        content_result: GamingContentPipelineResult,
        hosted_scene_images: tuple[HostedAsset, ...],
    ) -> tuple[VideoGenerationRequest, ...]:
        """Build scene-video requests only after hosted image references are available."""

        scene_visuals = self._build_aligned_scene_visuals(content_result)
        scene_motions = self._build_aligned_scene_motions(content_result)
        if not scene_visuals or not scene_motions:
            return ()
        if len(hosted_scene_images) != len(content_result.storyboard.scenes):
            raise CreatorOSValidationError(
                "hosted scene image count must match storyboard scene count",
                code="media_execution_hosted_reference_count_mismatch",
                details={
                    "storyboard_scene_count": len(content_result.storyboard.scenes),
                    "hosted_scene_image_count": len(hosted_scene_images),
                },
            )
        return tuple(
            VideoGenerationRequest(
                prompt=_build_scene_video_prompt(
                    content_result,
                    scene_plan,
                    scene_visuals[index],
                    scene_motions[index],
                ),
                duration_seconds=scene_plan.duration_seconds,
                reference_image=_build_hosted_reference_asset(hosted_scene_images[index]),
            )
            for index, scene_plan in enumerate(content_result.storyboard.scenes)
        )

    async def _cleanup_hosted_scene_images(
        self,
        *,
        hosted_scene_images: tuple[HostedAsset, ...],
        provider_selection: MediaProviderSelection | None,
    ) -> None:
        """Delete temporary hosted references without failing a successful production run."""

        if not hosted_scene_images:
            return
        selection = (
            MediaProviderSelection()
            if provider_selection is None
            else provider_selection
        )
        deleted_count = 0
        for hosted_asset in hosted_scene_images:
            try:
                deleted = await self.asset_hosting_service.delete_hosted_asset(
                    hosted_asset,
                    provider_name=selection.hosting_provider_name,
                )
            except Exception as error:
                self.logger.exception(
                    "media_execution_hosted_asset_cleanup_failed",
                    pipeline_name=PIPELINE_NAME,
                    provider_name=hosted_asset.provider_name,
                    provider_asset_id=hosted_asset.provider_asset_id,
                    error_type=type(error).__name__,
                )
                continue
            if deleted:
                deleted_count += 1
        self.logger.info(
            "media_execution_hosted_asset_cleanup_completed",
            pipeline_name=PIPELINE_NAME,
            hosted_asset_count=len(hosted_scene_images),
            deleted_count=deleted_count,
            success=True,
        )

    def _resolve_narration_voice(
        self,
        *,
        narration_direction: object,
    ) -> str | None:
        """Resolve narration voice using plan data first, then configured defaults."""

        explicit_voice = _normalize_optional_text(getattr(narration_direction, "voice", None))
        if explicit_voice is not None:
            return explicit_voice
        return _normalize_optional_text(self.media_generation_service.settings.default_tts_voice)

    def _validate_workspace_integrity(self, request: ApprovedMediaExecutionRequest) -> None:
        """Validate that the run workspace stays bounded and protected under artifact_root."""

        workspace = self.artifact_materialization_service.create_workspace(run_id=request.run_id)
        workspace_root = workspace.root_path
        try:
            workspace_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkflowError(
                "artifact root is not usable for production execution",
                code="media_execution_artifact_root_unusable",
            ) from error

        if not workspace_root.is_dir():
            raise WorkflowError(
                "artifact root is not a directory",
                code="media_execution_artifact_root_unusable",
            )

        workspace_path = workspace.workspace_path.resolve()
        if not workspace_path.is_relative_to(workspace_root.resolve()):
            raise WorkflowError(
                "workspace path escaped the configured artifact root",
                code="media_execution_workspace_outside_artifact_root",
                details={"run_id": request.run_id},
            )

        protected_output_path = workspace.video_dir / PROTECTED_FINAL_OUTPUT_FILENAME
        if protected_output_path.exists():
            raise ArtifactAlreadyExistsError(
                "final rendered output already exists for this run",
                code="media_execution_final_output_exists",
                details={"run_id": request.run_id, "filename": PROTECTED_FINAL_OUTPUT_FILENAME},
            )

    def _validate_assembly_preflight(
        self,
        request: ApprovedMediaExecutionRequest,
        media_request: MediaGenerationPackageRequest,
    ) -> None:
        """Validate that planned scene assets can assemble cleanly before generation begins."""

        placeholder_media = self._build_placeholder_generated_media(request, media_request)
        self.short_assembly_service.build_render_request(
            ShortAssemblyRequest(
                storyboard=request.content_result.storyboard,
                generated_media=placeholder_media,
                width=request.width,
                height=request.height,
                fps=request.fps,
                output_format=request.output_format,
            )
        )

    def _build_placeholder_generated_media(
        self,
        request: ApprovedMediaExecutionRequest,
        media_request: MediaGenerationPackageRequest,
    ) -> GeneratedMediaPackage:
        """Build one minimal synthetic media package for preflight-only assembly validation."""

        total_duration_seconds = request.content_result.storyboard.total_estimated_duration_seconds
        thumbnail = None
        if media_request.thumbnail_request is not None:
            thumbnail = GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="preflight://thumbnail.png"),
                provider_name="preflight",
                model="preflight",
                mime_type="image/png",
                width=1024,
                height=1024,
            )

        narration = None
        if media_request.narration_request is not None:
            narration = GeneratedAudio(
                artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="preflight://narration.wav"),
                provider_name="preflight",
                model="preflight",
                mime_type="audio/wav",
                estimated_duration_seconds=total_duration_seconds,
            )

        scene_images = tuple(
            GeneratedImage(
                artifact=GeneratedAsset(
                    asset_type=AssetType.IMAGE,
                    uri=f"preflight://scene_{index:03d}.png",
                ),
                provider_name="preflight",
                model="preflight",
                mime_type="image/png",
                width=1024,
                height=1024,
            )
            for index in range(1, len(media_request.scene_image_requests) + 1)
        )
        scene_videos = tuple(
            GeneratedVideo(
                artifact=GeneratedAsset(
                    asset_type=AssetType.VIDEO,
                    uri=f"preflight://clip_{index:03d}.mp4",
                ),
                provider_name="preflight",
                model="preflight",
                mime_type="video/mp4",
                duration_seconds=request.content_result.storyboard.scenes[index - 1].duration_seconds,
                width=request.width,
                height=request.height,
                fps=request.fps,
            )
            for index in range(1, len(media_request.scene_video_requests) + 1)
        )
        return GeneratedMediaPackage(
            thumbnail=thumbnail,
            narration=narration,
            scene_images=scene_images,
            scene_videos=scene_videos,
        )

    def _validate_result_integrity(
        self,
        result: MediaExecutionResult,
        *,
        request: ApprovedMediaExecutionRequest,
    ) -> None:
        """Validate the final typed production result before reporting success."""

        if result.run_id != request.run_id:
            raise CreatorOSValidationError(
                "result run_id did not match the approved request",
                code="media_execution_result_run_id_mismatch",
            )
        if result.materialized_media.workspace.run_id != request.run_id:
            raise CreatorOSValidationError(
                "materialized workspace run_id did not match the approved request",
                code="media_execution_workspace_run_id_mismatch",
            )
        if result.assembly.scene_count != len(request.content_result.storyboard.scenes):
            raise CreatorOSValidationError(
                "assembly scene count did not match the approved storyboard",
                code="media_execution_result_scene_count_mismatch",
            )

        rendered_video = result.assembly.rendered_video
        output_format = rendered_video.metadata.get("output_format", request.output_format)
        if _normalize_output_format(str(output_format)) != _normalize_output_format(request.output_format):
            raise CreatorOSValidationError(
                "rendered output format did not match the approved request",
                code="media_execution_result_output_format_mismatch",
            )
        if rendered_video.width != request.width or rendered_video.height != request.height:
            raise CreatorOSValidationError(
                "rendered dimensions did not match the approved request",
                code="media_execution_result_dimension_mismatch",
            )
        if rendered_video.fps != request.fps:
            raise CreatorOSValidationError(
                "rendered fps did not match the approved request",
                code="media_execution_result_fps_mismatch",
            )
        if rendered_video.duration_seconds <= 0:
            raise CreatorOSValidationError(
                "rendered duration must remain positive",
                code="media_execution_result_duration_invalid",
            )

        rendered_uri = rendered_video.artifact.uri
        if "://" not in rendered_uri:
            rendered_path = Path(rendered_uri).resolve()
            if not rendered_path.exists() or not rendered_path.is_file():
                raise CreatorOSValidationError(
                    "rendered local artifact does not exist",
                    code="media_execution_result_artifact_missing",
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
    provider_registry=None,
    media_generation_service: MediaGenerationService | None = None,
    asset_hosting_service: AssetHostingService | None = None,
    artifact_materialization_service: ArtifactMaterializationService | None = None,
    short_assembly_service: ShortAssemblyService | None = None,
    settings=None,
) -> MediaExecutionPipeline:
    """Create a safe mock-first approved media-execution pipeline."""

    from creatoros.services import (
        create_artifact_materialization_service,
        create_asset_hosting_service,
        create_media_generation_service,
        create_media_render_service,
        create_short_assembly_service,
    )

    resolved_media_generation_service = (
        create_media_generation_service(
            provider_registry=provider_registry,
            settings=settings,
        )
        if media_generation_service is None
        else media_generation_service
    )
    resolved_artifact_materialization_service = (
        create_artifact_materialization_service(settings=settings)
        if artifact_materialization_service is None
        else artifact_materialization_service
    )
    resolved_asset_hosting_service = (
        create_asset_hosting_service(
            provider_registry=provider_registry,
            settings=settings,
        )
        if asset_hosting_service is None
        else asset_hosting_service
    )
    resolved_short_assembly_service = (
        create_short_assembly_service(
            media_render_service=create_media_render_service(
                provider_registry=provider_registry,
                settings=settings,
            )
            if provider_registry is not None
            else None,
            settings=settings,
        )
        if short_assembly_service is None
        else short_assembly_service
    )
    return MediaExecutionPipeline(
        media_generation_service=resolved_media_generation_service,
        asset_hosting_service=resolved_asset_hosting_service,
        artifact_materialization_service=resolved_artifact_materialization_service,
        short_assembly_service=resolved_short_assembly_service,
    )


__all__ = [
    "PIPELINE_NAME",
    "STAGE_ARTIFACT_MATERIALIZATION",
    "STAGE_BUILD_ASSEMBLY_INPUTS",
    "STAGE_BUILD_MEDIA_REQUESTS",
    "STAGE_MEDIA_GENERATION",
    "STAGE_SHORT_ASSEMBLY",
    "STAGE_VALIDATE_REQUEST",
    "STAGE_VERIFY_HUMAN_APPROVAL",
    "STAGE_VERIFY_LIVE_CALL_POLICY",
    "STAGE_VERIFY_PUBLICATION_READINESS",
    "MediaExecutionPipeline",
    "create_media_execution_pipeline",
]
