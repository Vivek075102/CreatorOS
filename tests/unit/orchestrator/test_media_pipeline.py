"""Unit tests for the approved media-execution pipeline orchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.config import Settings
from creatoros.core import ApprovalRequiredError, CreatorOSValidationError, WorkflowError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.orchestrator import (
    ApprovedMediaExecutionRequest,
    GamingContentMediaPlanSet,
    GamingContentPipelineResult,
    GamingContentReviewSet,
    HumanApproval,
    MediaExecutionPipeline,
    MediaExecutionResult,
    create_media_execution_pipeline,
)
from creatoros.orchestrator.media_pipeline import (
    STAGE_MEDIA_GENERATION,
    STAGE_SHORT_ASSEMBLY,
)
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingOpportunityEvaluationOutput,
    GamingPublicationReadinessReviewOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    GamingTrendDiscoveryOutput,
    StoryboardSceneBreakdownOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    RenderedVideo,
    ShortRenderRequest,
)
from creatoros.services import (
    GeneratedMediaPackage,
    MediaGenerationPackageRequest,
    MediaGenerationService,
    MediaProviderSelection,
    ShortAssemblyRequest,
    ShortAssemblyResult,
    ShortAssemblyService,
    create_media_render_service,
)


def run_async(coro):
    """Execute async orchestrator calls in synchronous tests."""

    return asyncio.run(coro)


def build_settings() -> Settings:
    """Create isolated settings for mock-first execution tests."""

    project_root = Path("C:/GamingAIFactory")
    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider="mock",
        default_image_model=None,
        default_tts_provider="mock",
        default_tts_model=None,
        default_video_provider="mock",
        default_render_provider="mock",
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        assets_dir=project_root / "assets",
        logs_dir=project_root / "logs",
        prompts_dir=project_root / "prompts",
    )


def build_content_result(
    *,
    readiness_decision: str = "ready_for_human_review",
    scene_visuals: tuple[GamingSceneVisualOutput, ...] = (),
    scene_motions: tuple[GamingSceneMotionOutput, ...] = (),
) -> GamingContentPipelineResult:
    """Create one reusable pre-publication content result."""

    return GamingContentPipelineResult(
        trend_discovery=GamingTrendDiscoveryOutput(
            title="Roblox: Funny Myths",
            game="Roblox",
            topic="funny myths",
            angle="Test the funniest myth claims players keep repeating.",
            why_now="Players are actively sharing funny myth claims again.",
            source_summary="Supplied player discussions highlight repeated myth claims.",
            confidence="high",
        ),
        opportunity_evaluation=GamingOpportunityEvaluationOutput(
            decision="accept",
            score=86,
            strengths="The topic is curiosity-driven and easy to explain quickly.",
            risks="Claims must stay tied to supplied evidence.",
            recommended_angle="Test the most repeated funny myth claims with supplied evidence only.",
            hook_direction="Challenge a common Roblox belief immediately.",
            reason="The opportunity fits short-form myth-check content well.",
        ),
        opportunity={
            "title": "Roblox: Funny Myths",
            "game": "Roblox",
            "topic": "funny myths",
            "source": "supplied_research_signals",
            "opportunity_score": 86,
            "reasoning": "The opportunity fits short-form myth-check content well.",
            "estimated_duration_seconds": 30,
            "references": ["Supplied player discussions highlight repeated myth claims."],
        },
        script=YouTubeShortsScriptOutput(
            title="Roblox: Funny Myths",
            hook="You probably still believe this Roblox myth.",
            body="Players keep repeating one funny Roblox myth, but the supplied evidence says otherwise.",
            ending="That is why this funny myth does not hold up.",
            call_to_action="Which Roblox myth should we check next?",
            estimated_duration_seconds=30,
            evidence_note="Use supplied evidence only.",
        ),
        storyboard=StoryboardSceneBreakdownOutput.model_validate(
            {
                "storyboard_title": "Roblox: Funny Myths",
                "scenes": [
                    {
                        "scene_number": 1,
                        "purpose": "Open with the myth hook.",
                        "script_beat": "You probably still believe this Roblox myth.",
                        "visual": "Fast Roblox gameplay clip showing the myth setup.",
                        "on_screen_text": "Roblox myth?",
                        "duration_seconds": 10.0,
                    },
                    {
                        "scene_number": 2,
                        "purpose": "Explain what the supplied evidence supports.",
                        "script_beat": "Players keep repeating one funny Roblox myth, but the supplied evidence says otherwise.",
                        "visual": "Simple comparison shot between myth claim and evidence-backed outcome.",
                        "on_screen_text": "What the evidence says",
                        "duration_seconds": 20.0,
                    },
                ],
                "final_scene_count": 2,
                "total_estimated_duration_seconds": 30.0,
            }
        ),
        media_plans=GamingContentMediaPlanSet(
            thumbnail_concept=GamingThumbnailConceptOutput(
                concept="Show the myth claim versus reality.",
                focal_subject="A Roblox avatar reacting to the myth result.",
                background="Recognizable Roblox environment with motion blur.",
                composition="Large subject with bold side-by-side contrast.",
                expression_or_action="Surprised reaction at the myth result.",
                on_image_text="Myth?",
                style_direction="Clean readable contrast with playful energy.",
                avoid="Clutter and unsupported visual claims.",
                evidence_note="Derived from supplied evidence only.",
            ),
            narration_direction=GamingNarrationDirectionOutput(
                narration_text="You probably still believe this Roblox myth.",
                tone="Clear and engaging.",
                pace="Brisk but easy to follow.",
                emphasis="Stress the myth claim and the correction.",
                pause_guidance="Pause briefly before the correction.",
                pronunciation_notes="Say Roblox clearly.",
                target_duration_seconds=30,
            ),
            scene_visuals=scene_visuals,
            scene_motions=scene_motions,
        ),
        review_results=GamingContentReviewSet(
            script_quality=GamingScriptQualityReviewOutput(
                decision="accept",
                summary="The script is clear and focused.",
                hook_review="The hook creates immediate curiosity.",
                clarity_review="The script is easy to follow aloud.",
                structure_review="The idea stays focused.",
                factual_restraint="The claims remain cautious.",
                pacing_review="The pacing fits the target.",
                ending_review="The ending closes cleanly.",
                issues="None.",
                recommendations="Keep the phrasing concise.",
            ),
            evidence_consistency=GamingEvidenceConsistencyReviewOutput(
                decision="consistent",
                summary="The claims align with supplied evidence.",
                supported_claims="The main correction is supported.",
                unsupported_claims="None.",
                contradictions="None.",
                uncertainties="Minor uncertainty remains at the edge cases.",
                overstatements="None.",
                recommendations="Keep cautious wording.",
            ),
            storyboard_quality=GamingStoryboardQualityReviewOutput(
                decision="accept",
                summary="The storyboard supports the script well.",
                script_fidelity="The scenes match the script.",
                hook_scene="The first scene supports the hook.",
                scene_sequence="The scene order is clear.",
                visual_clarity="The visuals are understandable.",
                pacing="The pacing is balanced.",
                ending_scene="The closing scene lands clearly.",
                unsupported_visuals="None.",
                issues="None.",
                recommendations="Preserve the current structure.",
            ),
        ),
        publication_readiness=GamingPublicationReadinessReviewOutput(
            decision=readiness_decision,
            summary="The package is aligned for human review.",
            artifact_alignment="The title, script, storyboard, and plans are aligned.",
            evidence_status="The evidence review does not show unresolved contradictions.",
            missing_or_incomplete="None.",
            blockers="None.",
            non_blocking_improvements="Thumbnail text could be even shorter.",
            human_review_focus="Check final tone and branding.",
        ),
    )


def build_human_approval(*, approved: bool = True) -> HumanApproval:
    """Create one reusable explicit approval object."""

    return HumanApproval(approved=approved, approved_by="lead_editor")


def build_request(
    *,
    readiness_decision: str = "ready_for_human_review",
    approved: bool = True,
    provider_selection: MediaProviderSelection | None = None,
    render_provider_name: str | None = None,
    scene_visuals: tuple[GamingSceneVisualOutput, ...] = (),
    scene_motions: tuple[GamingSceneMotionOutput, ...] = (),
) -> ApprovedMediaExecutionRequest:
    """Create one reusable approved-media execution request."""

    return ApprovedMediaExecutionRequest(
        content_result=build_content_result(
            readiness_decision=readiness_decision,
            scene_visuals=scene_visuals,
            scene_motions=scene_motions,
        ),
        approval=build_human_approval(approved=approved),
        provider_selection=provider_selection,
        render_provider_name=render_provider_name,
    )


def build_scene_visuals() -> tuple[GamingSceneVisualOutput, ...]:
    """Create aligned optional scene-visual plans."""

    return (
        GamingSceneVisualOutput(
            scene_number=1,
            subject="A Roblox avatar",
            environment="Gameplay arena",
            action="Pointing at the myth claim",
            composition="Tight high-energy framing",
            mood="Playful",
            on_screen_text="Roblox myth?",
            style_direction="Bright readable contrast",
            negative_guidance="Avoid clutter",
        ),
        GamingSceneVisualOutput(
            scene_number=2,
            subject="Comparison screen",
            environment="Simple evidence board",
            action="Showing claim versus reality",
            composition="Split-screen comparison",
            mood="Clear",
            on_screen_text="What the evidence says",
            style_direction="Readable simple contrast",
            negative_guidance="Avoid unsupported claims",
        ),
    )


def build_scene_motions() -> tuple[GamingSceneMotionOutput, ...]:
    """Create aligned optional scene-motion plans."""

    return (
        GamingSceneMotionOutput(
            scene_number=1,
            primary_motion="Quick push-in",
            subject_movement="Avatar leans forward",
            camera_direction="Push toward subject",
            transition_guidance="Hard cut",
            pacing="Fast",
            duration_seconds=10.0,
            avoid="Avoid shaky motion",
        ),
        GamingSceneMotionOutput(
            scene_number=2,
            primary_motion="Slow pan",
            subject_movement="Panels slide apart",
            camera_direction="Pan left to right",
            transition_guidance="Hold cleanly",
            pacing="Measured",
            duration_seconds=20.0,
            avoid="Avoid cluttered motion",
        ),
    )


def build_generated_media_package() -> GeneratedMediaPackage:
    """Create one reusable generated-media package for spy services."""

    return GeneratedMediaPackage(
        thumbnail=GeneratedImage(
            artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/thumbnail.png"),
            provider_name="mock",
            model="mock-image-model",
            mime_type="image/png",
            width=1024,
            height=1024,
        ),
        narration=GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=30.0,
        ),
        scene_images=(
            GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene1.png"),
                provider_name="mock",
                model="mock-image-model",
                mime_type="image/png",
                width=1024,
                height=1024,
            ),
            GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene2.png"),
                provider_name="mock",
                model="mock-image-model",
                mime_type="image/png",
                width=1024,
                height=1024,
            ),
        ),
    )


def build_short_assembly_result(request: ShortAssemblyRequest) -> ShortAssemblyResult:
    """Create one reusable assembly result for spy services."""

    render_request = ShortRenderRequest(
        scenes=[
            {
                "scene_number": 1,
                "duration_seconds": 10.0,
                "visual_asset_ref": request.generated_media.scene_images[0].artifact,
                "caption_text": request.storyboard.scenes[0].on_screen_text,
            },
            {
                "scene_number": 2,
                "duration_seconds": 20.0,
                "visual_asset_ref": request.generated_media.scene_images[1].artifact,
                "caption_text": request.storyboard.scenes[1].on_screen_text,
            },
        ],
        narration=request.generated_media.narration,
    )
    rendered_video = RenderedVideo(
        artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://rendered/video/final.mp4"),
        provider_name="mock",
        mime_type="video/mp4",
        duration_seconds=30.0,
        width=1080,
        height=1920,
        fps=30.0,
    )
    return ShortAssemblyResult(
        render_request=render_request,
        rendered_video=rendered_video,
        generated_media=request.generated_media,
        scene_count=2,
        total_duration_seconds=30.0,
    )


class RecordingMediaGenerationService(MediaGenerationService):
    """Media-generation spy that records orchestrator calls."""

    def __init__(self) -> None:
        from creatoros.providers import create_provider_registry

        super().__init__(create_provider_registry(), build_settings())
        self.calls = 0
        self.last_request: MediaGenerationPackageRequest | None = None
        self.call_log: list[str] = []

    async def generate_package(self, request: MediaGenerationPackageRequest, *, context=None):  # type: ignore[override]
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        self.call_log.append(STAGE_MEDIA_GENERATION)
        return build_generated_media_package()


class FailingMediaGenerationService(RecordingMediaGenerationService):
    """Media-generation spy that fails immediately."""

    async def generate_package(self, request: MediaGenerationPackageRequest, *, context=None):  # type: ignore[override]
        await super().generate_package(request, context=context)
        raise WorkflowError("media generation failed", code="media_generation_failed")


class RecordingShortAssemblyService(ShortAssemblyService):
    """Short-assembly spy that records orchestrator calls."""

    def __init__(self) -> None:
        super().__init__(create_media_render_service(settings=build_settings()))
        self.calls = 0
        self.last_request: ShortAssemblyRequest | None = None
        self.last_render_provider_name: str | None = None
        self.call_log: list[str] = []

    async def assemble(self, request: ShortAssemblyRequest, *, render_provider_name: str | None = None):  # type: ignore[override]
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        self.last_render_provider_name = render_provider_name
        self.call_log.append(STAGE_SHORT_ASSEMBLY)
        return build_short_assembly_result(request)


class FailingShortAssemblyService(RecordingShortAssemblyService):
    """Short-assembly spy that fails immediately."""

    async def assemble(self, request: ShortAssemblyRequest, *, render_provider_name: str | None = None):  # type: ignore[override]
        await super().assemble(request, render_provider_name=render_provider_name)
        raise WorkflowError("short assembly failed", code="short_assembly_failed")


def build_spy_pipeline(
    *,
    media_generation_service: MediaGenerationService | None = None,
    short_assembly_service: ShortAssemblyService | None = None,
) -> tuple[MediaExecutionPipeline, RecordingMediaGenerationService, RecordingShortAssemblyService]:
    """Create one media-execution pipeline wired to recording service doubles."""

    resolved_generation = (
        RecordingMediaGenerationService()
        if media_generation_service is None
        else media_generation_service
    )
    resolved_assembly = (
        RecordingShortAssemblyService()
        if short_assembly_service is None
        else short_assembly_service
    )
    pipeline = MediaExecutionPipeline(
        media_generation_service=resolved_generation,
        short_assembly_service=resolved_assembly,
    )
    return pipeline, resolved_generation, resolved_assembly


def test_pipeline_accepts_required_service_dependencies() -> None:
    """The media pipeline should accept media generation and short assembly services."""

    pipeline, generation_service, assembly_service = build_spy_pipeline()

    assert pipeline.media_generation_service is generation_service
    assert pipeline.short_assembly_service is assembly_service


@pytest.mark.parametrize(
    ("dependency_name", "kwargs"),
    [
        ("media_generation_service", {"media_generation_service": object()}),
        ("short_assembly_service", {"short_assembly_service": object()}),
    ],
)
def test_pipeline_rejects_invalid_dependencies(
    dependency_name: str,
    kwargs: dict[str, object],
) -> None:
    """Invalid media-pipeline dependencies should fail safely."""

    _, generation_service, assembly_service = build_spy_pipeline()
    dependencies: dict[str, object] = {
        "media_generation_service": generation_service,
        "short_assembly_service": assembly_service,
    }
    dependencies.update(kwargs)

    with pytest.raises(CreatorOSValidationError, match=dependency_name):
        MediaExecutionPipeline(**dependencies)  # type: ignore[arg-type]


def test_explicit_positive_human_approval_is_accepted() -> None:
    """Positive approval should allow media-request construction."""

    pipeline, *_ = build_spy_pipeline()

    result = pipeline.build_media_generation_request(build_request(approved=True))

    assert isinstance(result, MediaGenerationPackageRequest)


def test_negative_human_approval_is_rejected_before_media_calls() -> None:
    """Negative approval must block the paid-media boundary entirely."""

    pipeline, generation_service, assembly_service = build_spy_pipeline()

    with pytest.raises(ApprovalRequiredError):
        run_async(pipeline.execute(build_request(approved=False)))

    assert generation_service.calls == 0
    assert assembly_service.calls == 0


def test_publication_readiness_is_distinct_from_human_approval() -> None:
    """Human approval must not override failed publication readiness."""

    pipeline, generation_service, assembly_service = build_spy_pipeline()

    with pytest.raises(WorkflowError) as exc_info:
        run_async(
            pipeline.execute(
                build_request(
                    readiness_decision="revise_before_human_review",
                    approved=True,
                )
            )
        )

    assert exc_info.value.code == "media_execution_not_publication_ready"
    assert generation_service.calls == 0
    assert assembly_service.calls == 0


def test_build_media_generation_request_maps_thumbnail_scene_images_and_narration_deterministically() -> None:
    """Approved planning outputs should map into deterministic provider-neutral media requests."""

    pipeline, *_ = build_spy_pipeline()
    source_request = build_request()
    original_dump = source_request.model_dump(mode="json")

    request = pipeline.build_media_generation_request(source_request)

    assert "Concept: Show the myth claim versus reality." in request.thumbnail_request.prompt
    assert "Scene number: 1." in request.scene_image_requests[0].prompt
    assert "Visual summary: Fast Roblox gameplay clip showing the myth setup." in request.scene_image_requests[0].prompt
    assert request.narration_request.text == "You probably still believe this Roblox myth."
    assert request.scene_video_requests == ()
    assert source_request.model_dump(mode="json") == original_dump


def test_scene_videos_map_only_when_scene_visuals_and_scene_motions_are_present() -> None:
    """Optional scene-video requests should exist only when actual typed planning data supports them."""

    pipeline, *_ = build_spy_pipeline()
    request = pipeline.build_media_generation_request(
        build_request(
            scene_visuals=build_scene_visuals(),
            scene_motions=build_scene_motions(),
        )
    )

    assert len(request.scene_video_requests) == 2
    assert request.scene_video_requests[0].duration_seconds == 10.0
    assert "Primary motion: Quick push-in." in request.scene_video_requests[0].prompt
    assert "Subject: A Roblox avatar." in request.scene_video_requests[0].prompt


def test_scene_visual_count_mismatch_fails_before_media_generation() -> None:
    """Partial scene-visual sets must fail instead of being silently ignored."""

    pipeline, *_ = build_spy_pipeline()

    with pytest.raises(CreatorOSValidationError) as exc_info:
        pipeline.build_media_generation_request(
            build_request(scene_visuals=build_scene_visuals()[:1])
        )

    assert exc_info.value.code == "media_execution_scene_visual_count_mismatch"


def test_scene_motion_duration_mismatch_fails_before_media_generation() -> None:
    """Scene-motion durations must align with storyboard timing when video plans are supplied."""

    pipeline, *_ = build_spy_pipeline()
    scene_motions = list(build_scene_motions())
    scene_motions[0] = scene_motions[0].model_copy(update={"duration_seconds": 11.0})

    with pytest.raises(CreatorOSValidationError) as exc_info:
        pipeline.build_media_generation_request(
            build_request(
                scene_visuals=build_scene_visuals(),
                scene_motions=tuple(scene_motions),
            )
        )

    assert exc_info.value.code == "media_execution_scene_motion_duration_mismatch"


def test_execute_calls_generation_once_then_assembly_once_and_forwards_overrides() -> None:
    """Execution should follow the deterministic service order and forward provider overrides."""

    pipeline, generation_service, assembly_service = build_spy_pipeline()
    request = build_request(
        provider_selection=MediaProviderSelection(
            image_provider_name="image-alt",
            tts_provider_name="tts-alt",
            video_provider_name="video-alt",
        ),
        render_provider_name="render-alt",
    )

    result = run_async(pipeline.execute(request))

    assert isinstance(result, MediaExecutionResult)
    assert generation_service.calls == 1
    assert assembly_service.calls == 1
    assert generation_service.last_request.provider_selection == request.provider_selection
    assert assembly_service.last_render_provider_name == "render-alt"
    assert assembly_service.last_request.storyboard == request.content_result.storyboard
    assert assembly_service.last_request.generated_media == result.generated_media
    assert result.assembly.rendered_video.artifact.uri == "mock://rendered/video/final.mp4"


def test_media_generation_failure_stops_before_assembly() -> None:
    """Generation failures should propagate and prevent assembly entirely."""

    generation_service = FailingMediaGenerationService()
    assembly_service = RecordingShortAssemblyService()
    pipeline, failing_generation, recording_assembly = build_spy_pipeline(
        media_generation_service=generation_service,
        short_assembly_service=assembly_service,
    )

    with pytest.raises(WorkflowError, match="media generation failed"):
        run_async(pipeline.execute(build_request()))

    assert failing_generation.calls == 1
    assert recording_assembly.calls == 0


def test_assembly_failure_propagates_without_fake_success() -> None:
    """Assembly failures should propagate after generation succeeds."""

    generation_service = RecordingMediaGenerationService()
    assembly_service = FailingShortAssemblyService()
    pipeline, recording_generation, failing_assembly = build_spy_pipeline(
        media_generation_service=generation_service,
        short_assembly_service=assembly_service,
    )

    with pytest.raises(WorkflowError, match="short assembly failed"):
        run_async(pipeline.execute(build_request()))

    assert recording_generation.calls == 1
    assert failing_assembly.calls == 1


def test_real_mock_end_to_end_execution_completes_offline() -> None:
    """The approved media pipeline should complete through real mock-first services offline."""

    pipeline = create_media_execution_pipeline(settings=build_settings())

    result = run_async(pipeline.execute(build_request()))

    assert result.content_result.final_stage == "publication_readiness_review"
    assert result.approval.approved is True
    assert result.generated_media.thumbnail is not None
    assert result.generated_media.thumbnail.artifact.uri.startswith("mock://generated/image/")
    assert result.assembly.render_request.narration is not None
    assert result.assembly.render_request.scenes[0].scene_number == 1
    assert result.assembly.render_request.scenes[1].scene_number == 2
    assert result.assembly.rendered_video.artifact.uri.startswith("mock://rendered/video/")
    assert all(
        scene.visual_asset_ref.uri != result.generated_media.thumbnail.artifact.uri
        for scene in result.assembly.render_request.scenes
    )


def test_pipeline_module_respects_boundaries_and_avoids_providers_agents_llms_and_publishing() -> None:
    """The media pipeline should use service boundaries only and stop before publishing."""

    module_source = Path("creatoros/orchestrator/media_pipeline.py").read_text(encoding="utf-8")

    assert "GamingResearchAgent" not in module_source
    assert "GamingScriptAgent" not in module_source
    assert "GamingStoryboardAgent" not in module_source
    assert "GamingMediaAgent" not in module_source
    assert "GamingReviewAgent" not in module_source
    assert "LLMExecutionService" not in module_source
    assert "ProviderRegistry" not in module_source
    assert "provider.generate" not in module_source
    assert "publish(" not in module_source
    assert "youtube" not in module_source.casefold()
    assert "openai" not in module_source.casefold()
    assert "ffmpeg" not in module_source.casefold()
    assert "moviepy" not in module_source.casefold()


def test_content_pipeline_source_still_stops_before_media_execution() -> None:
    """The existing content pipeline must remain pre-publication only."""

    module_source = Path("creatoros/orchestrator/content_pipeline.py").read_text(encoding="utf-8")

    assert "MediaGenerationService" not in module_source
    assert "ShortAssemblyService" not in module_source
    assert "MediaRenderService" not in module_source
    assert "ImageProvider" not in module_source
    assert "TTSProvider" not in module_source
    assert "VideoProvider" not in module_source
    assert "RenderProvider" not in module_source
