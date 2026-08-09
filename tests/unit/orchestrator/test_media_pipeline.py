"""Unit tests for the end-to-end approved short-production orchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.config import Settings
from creatoros.core import (
    ApprovalRequiredError,
    ArtifactAlreadyExistsError,
    ArtifactPathError,
    ConfigurationError,
    CreatorOSValidationError,
    ProviderNotFoundError,
    WorkflowError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.orchestrator import (
    ApprovedMediaExecutionRequest,
    GamingContentMediaPlanSet,
    GamingContentPipelineResult,
    GamingContentReviewSet,
    HumanApproval,
    MediaExecutionPipeline,
    MediaExecutionResult,
    ProductionExecutionPlan,
    create_media_execution_pipeline,
)
from creatoros.orchestrator.media_pipeline import (
    STAGE_ARTIFACT_MATERIALIZATION,
    STAGE_BUILD_ASSEMBLY_INPUTS,
    STAGE_MEDIA_GENERATION,
    STAGE_PREFLIGHT,
    STAGE_SHORT_ASSEMBLY,
)
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingOpportunityEvaluationOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    GamingTrendDiscoveryOutput,
    StoryboardSceneBreakdownOutput,
    StoryboardScenePlan,
    YouTubeShortsScriptOutput,
)
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    RenderedVideo,
)
from creatoros.providers.ffmpeg.render import FFmpegRenderProvider
from creatoros.providers.mock import create_mock_provider_registry
from creatoros.providers.openai.image import OpenAIImageProvider
from creatoros.providers.openai.tts import OpenAITTSProvider
from creatoros.services import (
    ArtifactMaterializationService,
    GeneratedMediaPackage,
    MaterializedArtifact,
    MaterializedMediaPackage,
    MediaGenerationPackageRequest,
    MediaGenerationService,
    MediaProviderSelection,
    ShortAssemblyRequest,
    ShortAssemblyResult,
    ShortAssemblyService,
    create_media_render_service,
)
from creatoros.services.artifact_materialization import ArtifactKind

MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
MINIMAL_WAV_BYTES = (
    b"RIFF(\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00"
    b"\x01\x00\x08\x00data\x04\x00\x00\x00\x80\x80\x80\x80"
)


def run_async(coro):
    """Execute async orchestrator calls in synchronous tests."""

    return asyncio.run(coro)


def build_settings(
    tmp_path: Path,
    *,
    default_image_provider: str = "mock",
    default_tts_provider: str = "mock",
    default_video_provider: str = "mock",
    default_render_provider: str = "mock",
    openai_api_key: str | None = None,
    default_image_model: str | None = None,
    default_tts_model: str | None = None,
    default_tts_voice: str = "alloy",
) -> Settings:
    """Create isolated settings for media-production tests."""

    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider=default_image_provider,
        default_image_model=(
            default_image_model
            if default_image_model is not None or default_image_provider == "mock"
            else "gpt-image-1"
        ),
        default_tts_provider=default_tts_provider,
        default_tts_model=(
            default_tts_model
            if default_tts_model is not None or default_tts_provider == "mock"
            else "gpt-4o-mini-tts"
        ),
        default_tts_voice=default_tts_voice,
        default_video_provider=default_video_provider,
        default_render_provider=default_render_provider,
        openai_api_key=openai_api_key,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=0,
        artifact_root=tmp_path / "artifacts",
        assets_dir=tmp_path / "assets",
        logs_dir=tmp_path / "logs",
        prompts_dir=tmp_path / "prompts",
    )


def build_content_result(*, readiness_decision: str = "ready_for_human_review") -> GamingContentPipelineResult:
    """Create one reusable approved content package for production tests."""

    scenes = (
        StoryboardScenePlan(
            scene_number=1,
            purpose="Open with the hook.",
            script_beat="You probably still believe this Roblox myth.",
            visual="Fast Roblox gameplay opener tied to the myth setup.",
            on_screen_text="Roblox Myth?",
            duration_seconds=10.0,
        ),
        StoryboardScenePlan(
            scene_number=2,
            purpose="Explain the correction clearly.",
            script_beat="Here is the quick evidence-backed explanation.",
            visual="Readable comparison between the myth and the supported explanation.",
            on_screen_text="Quick Breakdown",
            duration_seconds=12.0,
        ),
        StoryboardScenePlan(
            scene_number=3,
            purpose="Close with the CTA.",
            script_beat="What Roblox myth should we test next?",
            visual="Simple branded ending frame.",
            on_screen_text="What Next?",
            duration_seconds=8.0,
        ),
    )

    return GamingContentPipelineResult(
        trend_discovery=GamingTrendDiscoveryOutput(
            title="Roblox: Funny Myths",
            game="Roblox",
            topic="funny myths",
            angle="Test one repeated funny Roblox myth clearly.",
            why_now="The topic is useful for deterministic production validation.",
            source_summary="Deterministic approved package for short production tests.",
            confidence="high",
        ),
        opportunity_evaluation=GamingOpportunityEvaluationOutput(
            decision="accept",
            score=86,
            strengths="The topic is concise and easy to validate end to end.",
            risks="Claims should remain bounded to the approved package.",
            recommended_angle="Challenge one common Roblox assumption quickly.",
            hook_direction="Challenge the myth immediately.",
            reason="The package fits controlled short production.",
        ),
        opportunity={
            "title": "Roblox: Funny Myths",
            "game": "Roblox",
            "topic": "funny myths",
            "source": "approved_test_package",
            "opportunity_score": 86,
            "reasoning": "The package fits controlled short production.",
            "estimated_duration_seconds": 30,
            "references": ["Deterministic approved package for short production tests."],
        },
        script=YouTubeShortsScriptOutput(
            title="Roblox: Funny Myths",
            hook="You probably still believe this Roblox myth.",
            body="Here is the quick evidence-backed explanation.",
            ending="That is the quick Roblox breakdown.",
            call_to_action="What Roblox myth should we test next?",
            estimated_duration_seconds=30,
            evidence_note="Use the approved package only.",
        ),
        storyboard=StoryboardSceneBreakdownOutput(
            storyboard_title="Roblox: Funny Myths",
            scenes=scenes,
            final_scene_count=3,
            total_estimated_duration_seconds=30.0,
        ),
        media_plans=GamingContentMediaPlanSet(
            thumbnail_concept=GamingThumbnailConceptOutput(
                concept="Readable myth-versus-reality Roblox thumbnail.",
                focal_subject="One Roblox character reacting to the myth result.",
                background="Recognizable Roblox environment.",
                composition="Large subject with clean readable contrast.",
                expression_or_action="Surprised reaction.",
                on_image_text="Roblox Myth?",
                style_direction="Clean high-contrast short-form layout.",
                avoid="Clutter and unsupported claims.",
                evidence_note="Derived from the approved package only.",
            ),
            narration_direction=GamingNarrationDirectionOutput(
                narration_text=(
                    "You probably still believe this Roblox myth. "
                    "Here is the quick evidence-backed explanation. "
                    "That is the quick Roblox breakdown."
                ),
                tone="Clear and engaging.",
                pace="Brisk but readable.",
                emphasis="Stress the myth claim and the correction.",
                pause_guidance="Pause briefly before the correction.",
                pronunciation_notes="Say Roblox clearly.",
                target_duration_seconds=30,
            ),
        ),
        review_results=GamingContentReviewSet(
            script_quality=GamingScriptQualityReviewOutput(
                decision="accept",
                summary="The script is concise and readable.",
                hook_review="The hook is clear.",
                clarity_review="The narration is easy to follow.",
                structure_review="The structure is simple and ordered.",
                factual_restraint="The claims remain bounded.",
                pacing_review="The pacing fits the target duration.",
                ending_review="The ending closes cleanly.",
                issues="None.",
                recommendations="Preserve the approved structure.",
            ),
            evidence_consistency=GamingEvidenceConsistencyReviewOutput(
                decision="consistent",
                summary="The package is internally consistent.",
                supported_claims="The explanation is supported within the approved package.",
                unsupported_claims="None.",
                contradictions="None.",
                uncertainties="None.",
                overstatements="None.",
                recommendations="Keep the final short bounded to the approved request.",
            ),
            storyboard_quality=GamingStoryboardQualityReviewOutput(
                decision="accept",
                summary="The storyboard supports the script well.",
                script_fidelity="The scenes match the script beats.",
                hook_scene="The opening scene supports the hook.",
                scene_sequence="The scene order is clear and sequential.",
                visual_clarity="The visuals remain readable.",
                pacing="The scene pacing is balanced.",
                ending_scene="The ending scene closes the short well.",
                unsupported_visuals="None.",
                issues="None.",
                recommendations="Preserve the current storyboard.",
            ),
        ),
        publication_readiness=GamingPublicationReadinessReviewOutput(
            decision=readiness_decision,
            summary="The package is aligned for explicit human approval and production.",
            artifact_alignment="Title, script, storyboard, and media plans are aligned.",
            evidence_status="No unresolved conflicts remain in the approved package.",
            missing_or_incomplete="None.",
            blockers="None.",
            non_blocking_improvements="None.",
            human_review_focus="Confirm the package is ready to enter production execution.",
        ),
    )


def build_request(
    *,
    run_id: str = "run_001",
    readiness_decision: str = "ready_for_human_review",
    approved: bool = True,
    provider_selection: MediaProviderSelection | None = None,
    render_provider_name: str | None = None,
    confirm_live_media_calls: bool = False,
) -> ApprovedMediaExecutionRequest:
    """Create one reusable production request."""

    return ApprovedMediaExecutionRequest(
        content_result=build_content_result(readiness_decision=readiness_decision),
        approval=HumanApproval(approved=approved, approved_by="lead_editor"),
        run_id=run_id,
        provider_selection=provider_selection,
        render_provider_name=render_provider_name,
        confirm_live_media_calls=confirm_live_media_calls,
    )


def build_generated_media_package() -> GeneratedMediaPackage:
    """Create one generated media package for orchestration spies."""

    return GeneratedMediaPackage(
        thumbnail=GeneratedImage(
            artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/thumbnail.png"),
            provider_name="mock",
            model="mock-image-model",
            mime_type="image/png",
            width=1024,
            height=1024,
            payload_bytes=MINIMAL_PNG_BYTES,
        ),
        narration=GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=30.0,
            payload_bytes=MINIMAL_WAV_BYTES,
        ),
        scene_images=(
            GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene1.png"),
                provider_name="mock",
                model="mock-image-model",
                mime_type="image/png",
                width=1024,
                height=1024,
                payload_bytes=MINIMAL_PNG_BYTES,
            ),
            GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene2.png"),
                provider_name="mock",
                model="mock-image-model",
                mime_type="image/png",
                width=1024,
                height=1024,
                payload_bytes=MINIMAL_PNG_BYTES,
            ),
            GeneratedImage(
                artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/scene3.png"),
                provider_name="mock",
                model="mock-image-model",
                mime_type="image/png",
                width=1024,
                height=1024,
                payload_bytes=MINIMAL_PNG_BYTES,
            ),
        ),
    )


def build_materialized_media_package(
    package: GeneratedMediaPackage,
    *,
    artifact_root: Path,
    run_id: str,
) -> MaterializedMediaPackage:
    """Create one local materialized package for orchestration spy tests."""

    workspace_root = (artifact_root / run_id).resolve()
    return MaterializedMediaPackage(
        workspace={
            "run_id": run_id,
            "root_path": artifact_root,
        },
        thumbnail=(
            None
            if package.thumbnail is None
            else MaterializedArtifact(
                artifact_id=package.thumbnail.artifact.id,
                kind=ArtifactKind.IMAGE,
                path=workspace_root / "images" / "thumbnail.png",
                mime_type=package.thumbnail.mime_type,
                size_bytes=len(MINIMAL_PNG_BYTES),
                source_provider=package.thumbnail.provider_name,
            )
        ),
        narration=(
            None
            if package.narration is None
            else MaterializedArtifact(
                artifact_id=package.narration.artifact.id,
                kind=ArtifactKind.AUDIO,
                path=workspace_root / "audio" / "narration.wav",
                mime_type=package.narration.mime_type,
                size_bytes=len(MINIMAL_WAV_BYTES),
                source_provider=package.narration.provider_name,
            )
        ),
        scene_images=tuple(
            MaterializedArtifact(
                artifact_id=image.artifact.id,
                kind=ArtifactKind.IMAGE,
                path=workspace_root / "images" / f"scene_{index:03d}.png",
                mime_type=image.mime_type,
                size_bytes=len(MINIMAL_PNG_BYTES),
                source_provider=image.provider_name,
            )
            for index, image in enumerate(package.scene_images, start=1)
        ),
        scene_videos=(),
    )


class RecordingLogger:
    """Capture safe orchestrator logs for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append({"level": "info", "event": event, "kwargs": kwargs})

    def exception(self, event: str, **kwargs: object) -> None:
        self.events.append({"level": "error", "event": event, "kwargs": kwargs})


class RecordingMediaGenerationService(MediaGenerationService):
    """Generation spy that records orchestration handoffs."""

    def __init__(self, settings: Settings) -> None:
        provider_registry = create_mock_provider_registry()
        provider_registry.register(
            OpenAIImageProvider(
                api_key=settings.openai_api_key,
                default_model=settings.default_image_model,
                timeout_seconds=settings.provider_timeout_seconds,
                max_retries=settings.provider_max_retries,
            ),
            replace=True,
        )
        provider_registry.register(
            OpenAITTSProvider(
                api_key=settings.openai_api_key,
                default_model=settings.default_tts_model,
                timeout_seconds=settings.provider_timeout_seconds,
                max_retries=settings.provider_max_retries,
            ),
            replace=True,
        )
        super().__init__(provider_registry, settings)
        self.package_calls = 0
        self.image_calls = 0
        self.audio_calls = 0
        self.video_calls = 0
        self.last_request: MediaGenerationPackageRequest | None = None

    async def generate_image(self, request, *, provider_name: str | None = None, context=None):  # type: ignore[override]
        self.image_calls += 1
        del request, provider_name, context
        index = self.image_calls
        logical_name = "thumbnail" if index == 1 else f"scene{index - 1}"
        return GeneratedImage(
            artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri=f"mock://generated/image/{logical_name}.png"),
            provider_name="mock",
            model="mock-image-model",
            mime_type="image/png",
            width=1024,
            height=1024,
            payload_bytes=MINIMAL_PNG_BYTES,
        )

    async def generate_audio(self, request, *, provider_name: str | None = None, context=None):  # type: ignore[override]
        self.audio_calls += 1
        del request, provider_name, context
        return GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=30.0,
            payload_bytes=MINIMAL_WAV_BYTES,
        )

    async def generate_video(self, request, *, provider_name: str | None = None, context=None):  # type: ignore[override]
        self.video_calls += 1
        del request, provider_name, context
        return GeneratedVideo(
            artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri=f"mock://generated/video/clip{self.video_calls}.mp4"),
            provider_name="mock",
            model="mock-video-model",
            mime_type="video/mp4",
            duration_seconds=5.0,
        )

    async def generate_package(self, request: MediaGenerationPackageRequest, *, context=None):  # type: ignore[override]
        self.package_calls += 1
        self.last_request = request.model_copy(deep=True)
        return await super().generate_package(request, context=context)


class FailingMediaGenerationService(RecordingMediaGenerationService):
    """Generation spy that fails immediately."""

    async def generate_package(self, request: MediaGenerationPackageRequest, *, context=None):  # type: ignore[override]
        await super().generate_package(request, context=context)
        raise WorkflowError("media generation failed", code="media_generation_failed")


class RecordingArtifactMaterializationService(ArtifactMaterializationService):
    """Materialization spy that records handoffs without filesystem writes."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls = 0
        self.last_package: GeneratedMediaPackage | None = None
        self.last_run_id: str | None = None

    def materialize_package(self, package: GeneratedMediaPackage, *, run_id: str) -> MaterializedMediaPackage:  # type: ignore[override]
        self.calls += 1
        self.last_package = package.model_copy(deep=True)
        self.last_run_id = run_id
        return build_materialized_media_package(
            package,
            artifact_root=self.settings.artifact_root,
            run_id=run_id,
        )


class FailingArtifactMaterializationService(RecordingArtifactMaterializationService):
    """Materialization spy that fails immediately."""

    def materialize_package(self, package: GeneratedMediaPackage, *, run_id: str) -> MaterializedMediaPackage:  # type: ignore[override]
        super().materialize_package(package, run_id=run_id)
        raise WorkflowError("materialization failed", code="materialization_failed")


class RecordingShortAssemblyService(ShortAssemblyService):
    """Assembly spy that records local handoffs and returns a deterministic local result."""

    def __init__(self, settings: Settings) -> None:
        provider_registry = create_mock_provider_registry()
        provider_registry.register(
            FFmpegRenderProvider(
                artifact_root=settings.artifact_root,
                ffmpeg_path="ffmpeg",
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            replace=True,
        )
        super().__init__(create_media_render_service(provider_registry=provider_registry, settings=settings))
        self.calls = 0
        self.last_request: ShortAssemblyRequest | None = None
        self.last_render_provider_name: str | None = None

    async def assemble(self, request: ShortAssemblyRequest, *, render_provider_name: str | None = None):  # type: ignore[override]
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        self.last_render_provider_name = render_provider_name
        render_request = self.build_render_request(request)
        first_scene_asset = render_request.scenes[0].visual_asset_ref
        assert first_scene_asset is not None
        first_scene_path = Path(first_scene_asset.uri)
        final_video_path = first_scene_path.parents[1] / "video" / "final_short.mp4"
        final_video_path.parent.mkdir(parents=True, exist_ok=True)
        final_video_path.write_bytes(b"mock-rendered-video")
        return ShortAssemblyResult(
            render_request=render_request,
            rendered_video=RenderedVideo(
                artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri=str(final_video_path)),
                provider_name=render_provider_name or "mock",
                mime_type="video/mp4",
                duration_seconds=render_request.total_duration_seconds,
                width=render_request.width,
                height=render_request.height,
                fps=render_request.fps,
                metadata={"output_format": render_request.output_format},
            ),
            generated_media=request.generated_media,
            scene_count=len(render_request.scenes),
            total_duration_seconds=render_request.total_duration_seconds,
        )


class FailingShortAssemblyService(RecordingShortAssemblyService):
    """Assembly spy that fails immediately."""

    async def assemble(self, request: ShortAssemblyRequest, *, render_provider_name: str | None = None):  # type: ignore[override]
        await super().assemble(request, render_provider_name=render_provider_name)
        raise WorkflowError("assembly failed", code="assembly_failed")


def build_spy_pipeline(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    media_generation_service: MediaGenerationService | None = None,
    artifact_materialization_service: ArtifactMaterializationService | None = None,
    short_assembly_service: ShortAssemblyService | None = None,
) -> tuple[
    MediaExecutionPipeline,
    MediaGenerationService,
    ArtifactMaterializationService,
    ShortAssemblyService,
]:
    """Create one production pipeline wired to recording test doubles."""

    resolved_settings = build_settings(tmp_path) if settings is None else settings
    resolved_generation = (
        RecordingMediaGenerationService(resolved_settings)
        if media_generation_service is None
        else media_generation_service
    )
    resolved_materializer = (
        RecordingArtifactMaterializationService(resolved_settings)
        if artifact_materialization_service is None
        else artifact_materialization_service
    )
    resolved_assembly = (
        RecordingShortAssemblyService(resolved_settings)
        if short_assembly_service is None
        else short_assembly_service
    )
    pipeline = MediaExecutionPipeline(
        media_generation_service=resolved_generation,
        artifact_materialization_service=resolved_materializer,
        short_assembly_service=resolved_assembly,
    )
    return pipeline, resolved_generation, resolved_materializer, resolved_assembly


def test_pipeline_accepts_required_dependencies(tmp_path: Path) -> None:
    """The production pipeline should accept generation, materialization, and assembly services."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)

    assert pipeline.media_generation_service is generation_service
    assert pipeline.artifact_materialization_service is materializer
    assert pipeline.short_assembly_service is assembly_service


@pytest.mark.parametrize(
    ("dependency_name", "kwargs"),
    [
        ("media_generation_service", {"media_generation_service": object()}),
        ("artifact_materialization_service", {"artifact_materialization_service": object()}),
        ("short_assembly_service", {"short_assembly_service": object()}),
    ],
)
def test_pipeline_rejects_invalid_dependencies(
    tmp_path: Path,
    dependency_name: str,
    kwargs: dict[str, object],
) -> None:
    """Invalid production-pipeline dependencies should fail safely."""

    settings = build_settings(tmp_path)
    dependencies: dict[str, object] = {
        "media_generation_service": RecordingMediaGenerationService(settings),
        "artifact_materialization_service": RecordingArtifactMaterializationService(settings),
        "short_assembly_service": RecordingShortAssemblyService(settings),
    }
    dependencies.update(kwargs)

    with pytest.raises(CreatorOSValidationError, match=dependency_name):
        MediaExecutionPipeline(**dependencies)  # type: ignore[arg-type]


def test_unapproved_content_is_rejected_before_any_downstream_stage(tmp_path: Path) -> None:
    """Approval must be validated before generation, materialization, or assembly begin."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)

    with pytest.raises(ApprovalRequiredError) as exc_info:
        run_async(pipeline.execute(build_request(approved=False)))

    assert exc_info.value.code == "media_execution_approval_required"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_publication_readiness_failure_blocks_all_later_stages(tmp_path: Path) -> None:
    """Content that is not ready for human review must never enter production."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)

    with pytest.raises(WorkflowError) as exc_info:
        run_async(
            pipeline.execute(
                build_request(readiness_decision="revise_before_human_review")
            )
        )

    assert exc_info.value.code == "media_execution_not_publication_ready"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_non_mock_media_provider_requires_explicit_live_confirmation(tmp_path: Path) -> None:
    """Live media provider selection must fail before any provider call without confirmation."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request(
        provider_selection=MediaProviderSelection(image_provider_name="openai-image")
    )

    with pytest.raises(ApprovalRequiredError) as exc_info:
        run_async(pipeline.execute(request))

    assert exc_info.value.code == "media_execution_live_confirmation_required"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_mock_preflight_builds_deterministic_plan_without_execution(tmp_path: Path) -> None:
    """Offline preflight should build a stable plan and avoid every execution stage."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)

    first_plan = pipeline.build_execution_plan(build_request(run_id="planned_run"))
    second_plan = pipeline.build_execution_plan(build_request(run_id="planned_run"))

    assert isinstance(first_plan, ProductionExecutionPlan)
    assert first_plan == second_plan
    assert first_plan.run_id == "planned_run"
    assert first_plan.scene_count == 3
    assert first_plan.image_generation_count == 4
    assert first_plan.tts_generation_count == 1
    assert first_plan.video_generation_count == 0
    assert first_plan.live_media_call_count == 0
    assert first_plan.will_use_live_media is False
    assert first_plan.execution_started is False
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_live_provider_plan_reports_live_call_counts_without_confirmation(tmp_path: Path) -> None:
    """Plan mode should expose live-call counts without starting execution or needing confirmation."""

    settings = build_settings(
        tmp_path,
        default_image_provider="openai-image",
        default_tts_provider="openai-tts",
        openai_api_key="sk-test-secret",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )

    plan = pipeline.build_execution_plan(build_request())

    assert plan.image_provider == "openai-image"
    assert plan.tts_provider == "openai-tts"
    assert plan.image_generation_count == 4
    assert plan.tts_generation_count == 1
    assert plan.video_generation_count == 0
    assert plan.live_media_call_count == 5
    assert plan.will_use_live_media is True
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_media_generation_request_includes_default_tts_voice(tmp_path: Path) -> None:
    """Production request mapping should include the configured default narration voice."""

    settings = build_settings(tmp_path)
    pipeline, *_ = build_spy_pipeline(tmp_path, settings=settings)

    media_request = pipeline.build_media_generation_request(build_request())

    assert media_request.narration_request is not None
    assert media_request.narration_request.voice == "alloy"
    assert media_request.narration_request.text == (
        "You probably still believe this Roblox myth. "
        "Here is the quick evidence-backed explanation. "
        "That is the quick Roblox breakdown."
    )


def test_media_generation_request_honors_configured_default_tts_voice(tmp_path: Path) -> None:
    """Production request mapping should honor an explicitly configured default narration voice."""

    settings = build_settings(tmp_path, default_tts_voice="nova")
    pipeline, *_ = build_spy_pipeline(tmp_path, settings=settings)

    media_request = pipeline.build_media_generation_request(build_request())

    assert media_request.narration_request is not None
    assert media_request.narration_request.voice == "nova"


def test_openai_tts_preflight_rejects_missing_voice_before_any_media_generation(tmp_path: Path) -> None:
    """Live narration should fail preflight before any image or TTS call when voice is missing."""

    settings = build_settings(
        tmp_path,
        default_image_provider="openai-image",
        default_tts_provider="openai-tts",
        openai_api_key="sk-test-secret",
        default_tts_voice="   ",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )
    request = build_request(
        provider_selection=MediaProviderSelection(
            image_provider_name="openai-image",
            tts_provider_name="openai-tts",
        ),
        confirm_live_media_calls=True,
    )

    with pytest.raises(ConfigurationError) as exc_info:
        run_async(pipeline.execute(request))

    assert exc_info.value.code == "media_execution_missing_live_configuration"
    assert generation_service.package_calls == 0
    assert generation_service.image_calls == 0
    assert generation_service.audio_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0
    assert "sk-test-secret" not in str(exc_info.value)


def test_openai_tts_preflight_rejects_unsupported_voice_before_any_media_generation(
    tmp_path: Path,
) -> None:
    """Unsupported live narration voices should fail before any paid image or TTS work begins."""

    settings = build_settings(
        tmp_path,
        default_image_provider="openai-image",
        default_tts_provider="openai-tts",
        openai_api_key="sk-test-secret",
        default_tts_voice="robot",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )
    request = build_request(
        provider_selection=MediaProviderSelection(
            image_provider_name="openai-image",
            tts_provider_name="openai-tts",
        ),
        confirm_live_media_calls=True,
    )

    with pytest.raises(CreatorOSValidationError) as exc_info:
        run_async(pipeline.execute(request))

    assert exc_info.value.code == "media_execution_invalid_voice"
    assert generation_service.package_calls == 0
    assert generation_service.image_calls == 0
    assert generation_service.audio_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_openai_tts_preflight_accepts_supported_voice_without_generation(tmp_path: Path) -> None:
    """Supported live narration voices should pass plan-time preflight cleanly."""

    settings = build_settings(
        tmp_path,
        default_tts_provider="openai-tts",
        openai_api_key="sk-test-secret",
        default_tts_voice="nova",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )

    plan = pipeline.build_execution_plan(build_request())

    assert plan.tts_provider == "openai-tts"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_plan_rejects_invalid_dimensions_before_generation(tmp_path: Path) -> None:
    """Preflight should catch invalid dimensions even for manually constructed requests."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request().model_copy(update={"width": 0})

    with pytest.raises(CreatorOSValidationError) as exc_info:
        pipeline.build_execution_plan(request)

    assert exc_info.value.code == "media_execution_invalid_dimensions"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_plan_rejects_invalid_fps_before_generation(tmp_path: Path) -> None:
    """Preflight should catch non-positive or non-finite fps values."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request().model_copy(update={"fps": 0.0})

    with pytest.raises(CreatorOSValidationError) as exc_info:
        pipeline.build_execution_plan(request)

    assert exc_info.value.code == "media_execution_invalid_fps"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_plan_rejects_unsupported_output_format_before_generation(tmp_path: Path) -> None:
    """Preflight should reject unsupported final output formats safely."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request().model_copy(update={"output_format": "mov"})

    with pytest.raises(CreatorOSValidationError) as exc_info:
        pipeline.build_execution_plan(request)

    assert exc_info.value.code == "media_execution_output_format_unsupported"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_unknown_provider_fails_preflight_before_generation(tmp_path: Path) -> None:
    """Unknown provider names should fail during preflight rather than during generation."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request(
        provider_selection=MediaProviderSelection(image_provider_name="missing-image"),
    )

    with pytest.raises(ProviderNotFoundError):
        pipeline.build_execution_plan(request)

    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_missing_live_configuration_fails_preflight_before_provider_invocation(tmp_path: Path) -> None:
    """Live-provider preflight should fail before generation when required config is missing."""

    settings = build_settings(
        tmp_path,
        default_image_provider="openai-image",
        openai_api_key="sk-test-secret",
    ).model_copy(update={"default_image_model": None})
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )

    with pytest.raises(ConfigurationError) as exc_info:
        pipeline.build_execution_plan(build_request())

    assert exc_info.value.code == "media_execution_missing_live_configuration"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_existing_final_output_is_protected_during_preflight(tmp_path: Path) -> None:
    """A protected final video path should fail before any media generation begins."""

    settings = build_settings(tmp_path)
    protected_output = settings.artifact_root / "run_001" / "video" / "final_short.mp4"
    protected_output.parent.mkdir(parents=True, exist_ok=True)
    protected_output.write_bytes(b"existing-final")
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )

    with pytest.raises(ArtifactAlreadyExistsError) as exc_info:
        pipeline.build_execution_plan(build_request())

    assert exc_info.value.code == "media_execution_final_output_exists"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_plan_does_not_include_secrets_or_prompt_text(tmp_path: Path) -> None:
    """Execution plans should remain operational summaries rather than content payloads."""

    settings = build_settings(tmp_path, openai_api_key="sk-test-secret")
    pipeline, *_ = build_spy_pipeline(tmp_path, settings=settings)

    plan_dump = pipeline.build_execution_plan(build_request()).model_dump_json()

    assert "sk-test-secret" not in plan_dump
    assert "You probably still believe this Roblox myth." not in plan_dump
    assert "Title:" not in plan_dump


def test_api_key_presence_alone_does_not_authorize_live_execution(tmp_path: Path) -> None:
    """Configured credentials must not bypass the explicit live-call confirmation gate."""

    settings = build_settings(
        tmp_path,
        default_image_provider="openai-image",
        openai_api_key="sk-test-secret",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )

    with pytest.raises(ApprovalRequiredError) as exc_info:
        run_async(pipeline.execute(build_request()))

    assert exc_info.value.code == "media_execution_live_confirmation_required"
    assert generation_service.package_calls == 0
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_live_media_provider_is_allowed_when_confirmation_is_explicit(tmp_path: Path) -> None:
    """Explicit confirmation should allow non-mock media provider policy to pass."""

    settings = build_settings(
        tmp_path,
        openai_api_key="sk-test-secret",
        default_image_provider="openai-image",
        default_tts_provider="openai-tts",
    )
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
    )
    request = build_request(
        provider_selection=MediaProviderSelection(
            image_provider_name="openai-image",
            tts_provider_name="openai-tts",
        ),
        confirm_live_media_calls=True,
    )

    result = run_async(pipeline.execute(request))

    assert isinstance(result, MediaExecutionResult)
    assert generation_service.package_calls == 1
    assert materializer.calls == 1
    assert assembly_service.calls == 1


def test_ffmpeg_render_selection_does_not_require_live_media_confirmation(tmp_path: Path) -> None:
    """Local FFmpeg rendering is not itself a paid live media provider boundary."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request(render_provider_name="ffmpeg")

    result = run_async(pipeline.execute(request))

    assert result.render_provider_name == "ffmpeg"
    assert generation_service.package_calls == 1
    assert materializer.calls == 1
    assert assembly_service.calls == 1


def test_request_rejects_unsafe_run_id() -> None:
    """Traversal-style run IDs should fail at the typed request boundary."""

    with pytest.raises(ArtifactPathError, match="unsafe path characters"):
        build_request(run_id="../bad")


def test_execute_preserves_run_id_and_handoffs_local_materialized_assets(tmp_path: Path) -> None:
    """The production pipeline should preserve the run ID through all handoff stages."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request(
        run_id="roblox_short_run",
        provider_selection=MediaProviderSelection(
            image_provider_name="mock",
            tts_provider_name="mock",
            video_provider_name="mock",
        ),
        render_provider_name="mock",
    )

    result = run_async(pipeline.execute(request))

    assert isinstance(result, MediaExecutionResult)
    assert result.run_id == "roblox_short_run"
    assert generation_service.last_request is not None
    assert generation_service.last_request.provider_selection == request.provider_selection
    assert materializer.last_package == result.generated_media
    assert materializer.last_run_id == "roblox_short_run"
    assert result.materialized_media.workspace.run_id == "roblox_short_run"
    assert assembly_service.last_request is not None
    assert assembly_service.last_render_provider_name == "mock"
    assert [scene.scene_number for scene in assembly_service.last_request.storyboard.scenes] == [1, 2, 3]
    assert assembly_service.last_request.generated_media.narration is not None
    assert assembly_service.last_request.generated_media.narration.artifact.uri.endswith(
        "audio\\narration.wav"
    ) or assembly_service.last_request.generated_media.narration.artifact.uri.endswith("audio/narration.wav")
    assert assembly_service.last_request.generated_media.scene_images[0].artifact.uri.endswith(
        "images\\scene_001.png"
    ) or assembly_service.last_request.generated_media.scene_images[0].artifact.uri.endswith("images/scene_001.png")
    assert result.assembly.render_request.scenes[0].caption_text == "Roblox Myth?"
    assert result.assembly.render_request.narration is not None
    assert result.assembly.rendered_video.artifact.uri.endswith(
        "video\\final_short.mp4"
    ) or result.assembly.rendered_video.artifact.uri.endswith("video/final_short.mp4")
    assert "payload_bytes" not in result.model_dump()


def test_planned_call_counts_match_executed_mock_call_counts(tmp_path: Path) -> None:
    """Preflight call counts should match the actual deterministic mock execution counts."""

    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(tmp_path)
    request = build_request(run_id="count_match_run")

    plan = pipeline.build_execution_plan(request)
    result = run_async(pipeline.execute(request))

    assert result.run_id == "count_match_run"
    assert plan.image_generation_count == generation_service.image_calls
    assert plan.tts_generation_count == generation_service.audio_calls
    assert plan.video_generation_count == generation_service.video_calls
    assert generation_service.package_calls == 1
    assert materializer.calls == 1
    assert assembly_service.calls == 1


def test_media_generation_failure_stops_materialization_and_assembly(tmp_path: Path) -> None:
    """Generation failures should prevent every later stage from running."""

    settings = build_settings(tmp_path)
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
        media_generation_service=FailingMediaGenerationService(settings),
    )

    with pytest.raises(WorkflowError, match="media generation failed"):
        run_async(pipeline.execute(build_request()))

    assert generation_service.package_calls == 1
    assert materializer.calls == 0
    assert assembly_service.calls == 0


def test_materialization_failure_stops_assembly(tmp_path: Path) -> None:
    """Materialization failures should prevent render assembly entirely."""

    settings = build_settings(tmp_path)
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
        artifact_materialization_service=FailingArtifactMaterializationService(settings),
    )

    with pytest.raises(WorkflowError, match="materialization failed"):
        run_async(pipeline.execute(build_request()))

    assert generation_service.package_calls == 1
    assert materializer.calls == 1
    assert assembly_service.calls == 0


def test_assembly_failure_propagates_without_false_success(tmp_path: Path) -> None:
    """Assembly failures should surface cleanly after earlier stages succeed."""

    settings = build_settings(tmp_path)
    pipeline, generation_service, materializer, assembly_service = build_spy_pipeline(
        tmp_path,
        settings=settings,
        short_assembly_service=FailingShortAssemblyService(settings),
    )

    with pytest.raises(WorkflowError, match="assembly failed"):
        run_async(pipeline.execute(build_request()))

    assert generation_service.package_calls == 1
    assert materializer.calls == 1
    assert assembly_service.calls == 1


def test_assembly_failure_preserves_materialized_artifacts_for_diagnostics(tmp_path: Path) -> None:
    """Later-stage failures should keep successfully materialized artifacts in the run workspace."""

    settings = build_settings(tmp_path)
    pipeline = create_media_execution_pipeline(
        settings=settings,
        short_assembly_service=FailingShortAssemblyService(settings),
    )

    with pytest.raises(WorkflowError):
        run_async(pipeline.execute(build_request(run_id="diagnostic_run")))

    workspace = settings.artifact_root / "diagnostic_run"
    assert (workspace / "images" / "thumbnail.png").is_file()
    assert (workspace / "audio" / "narration.wav").is_file()
    assert (workspace / "images" / "scene_001.png").is_file()


def test_failure_category_is_added_to_stage_errors(tmp_path: Path) -> None:
    """Stage failures should expose a safe failure category without leaking content."""

    settings = build_settings(tmp_path)
    pipeline, *_ = build_spy_pipeline(
        tmp_path,
        settings=settings,
        short_assembly_service=FailingShortAssemblyService(settings),
    )

    with pytest.raises(WorkflowError) as exc_info:
        run_async(pipeline.execute(build_request()))

    assert exc_info.value.details["stage"] == STAGE_SHORT_ASSEMBLY
    assert exc_info.value.details["failure_category"] == "render_failed"


def test_real_mock_end_to_end_execution_completes_fully_offline(tmp_path: Path) -> None:
    """The real mock-first pipeline should complete without network or FFmpeg."""

    settings = build_settings(tmp_path)
    pipeline = create_media_execution_pipeline(settings=settings)

    result = run_async(pipeline.execute(build_request(run_id="offline_mock_run")))

    assert result.run_id == "offline_mock_run"
    assert result.generated_media.thumbnail is not None
    assert result.materialized_media.workspace.workspace_path == settings.artifact_root / "offline_mock_run"
    assert result.materialized_media.thumbnail is not None
    assert result.materialized_media.thumbnail.path.is_file()
    assert result.materialized_media.narration is not None
    assert result.materialized_media.narration.path.is_file()
    assert len(result.materialized_media.scene_images) == 3
    assert all(artifact.path.is_file() for artifact in result.materialized_media.scene_images)
    assert all(
        scene.visual_asset_ref is not None and Path(scene.visual_asset_ref.uri).is_file()
        for scene in result.assembly.render_request.scenes
    )
    assert result.assembly.rendered_video.artifact.uri.startswith("mock://rendered/video/")


def test_existing_output_workspace_artifacts_are_not_silently_overwritten(tmp_path: Path) -> None:
    """Existing workspace outputs should preserve the current no-overwrite behavior."""

    settings = build_settings(tmp_path)
    workspace_images_dir = settings.artifact_root / "run_001" / "images"
    workspace_images_dir.mkdir(parents=True, exist_ok=True)
    (workspace_images_dir / "thumbnail.png").write_bytes(MINIMAL_PNG_BYTES)
    pipeline = create_media_execution_pipeline(settings=settings)

    with pytest.raises(ArtifactAlreadyExistsError):
        run_async(pipeline.execute(build_request()))


def test_success_logs_safe_stage_metadata_only(tmp_path: Path) -> None:
    """Lifecycle logs should expose only safe production metadata."""

    pipeline, *_ = build_spy_pipeline(tmp_path)
    logger = RecordingLogger()
    pipeline.logger = logger

    result = run_async(pipeline.execute(build_request(run_id="logged_run")))

    assert result.run_id == "logged_run"
    stage_events = [
        event["kwargs"]["stage"]
        for event in logger.events
        if event["event"] == "media_execution_stage_completed"
    ]
    assert stage_events == [
        STAGE_MEDIA_GENERATION,
        STAGE_ARTIFACT_MATERIALIZATION,
        STAGE_SHORT_ASSEMBLY,
    ]
    combined = "".join(str(event) for event in logger.events)
    assert any(event["event"] == "production_preflight_started" for event in logger.events)
    assert any(event["event"] == "production_preflight_completed" for event in logger.events)
    assert any(event["event"] == "production_plan_created" for event in logger.events)
    assert STAGE_BUILD_ASSEMBLY_INPUTS not in stage_events
    assert STAGE_PREFLIGHT not in stage_events
    assert "sk-test-secret" not in combined
    assert "You probably still believe this Roblox myth." not in combined
    assert "Roblox Myth?" not in combined
