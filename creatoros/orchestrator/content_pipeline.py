"""Integrated provider-independent AI content pipeline for CreatorOS."""

from __future__ import annotations

from creatoros.agents import (
    GamingEvidenceConsistencyReviewRequest,
    GamingMediaAgent,
    GamingNarrationDirectionRequest,
    GamingOpportunityEvaluationRequest,
    GamingPublicationReadinessReviewRequest,
    GamingResearchAgent,
    GamingReviewAgent,
    GamingScriptAgent,
    GamingScriptGenerationRequest,
    GamingScriptQualityReviewRequest,
    GamingStoryboardAgent,
    GamingStoryboardQualityReviewRequest,
    GamingStoryboardSceneBreakdownRequest,
    GamingThumbnailConceptRequest,
    GamingTrendDiscoveryRequest,
    ResearchExecutionOptions,
)
from creatoros.core import CreatorOSError, CreatorOSValidationError, WorkflowError
from creatoros.domain import ContentOpportunity
from creatoros.observability import get_logger
from creatoros.orchestrator.models import (
    GamingContentMediaPlanSet,
    GamingContentPipelineRequest,
    GamingContentPipelineResult,
    GamingContentReviewSet,
)
from creatoros.services import LLMExecutionService

PIPELINE_NAME = "gaming_content_pipeline"
STAGE_TREND_DISCOVERY = "trend_discovery"
STAGE_OPPORTUNITY_EVALUATION = "opportunity_evaluation"
STAGE_SCRIPT_GENERATION = "script_generation"
STAGE_STORYBOARD_SCENE_BREAKDOWN = "storyboard_scene_breakdown"
STAGE_THUMBNAIL_CONCEPT = "thumbnail_concept"
STAGE_NARRATION_DIRECTION = "narration_direction"
STAGE_SCRIPT_QUALITY_REVIEW = "script_quality_review"
STAGE_EVIDENCE_CONSISTENCY_REVIEW = "evidence_consistency_review"
STAGE_STORYBOARD_QUALITY_REVIEW = "storyboard_quality_review"
STAGE_PUBLICATION_READINESS_REVIEW = "publication_readiness_review"


def _serialize_research_signals(research_signals: tuple[str, ...]) -> str:
    """Convert normalized research-signal items into one stable prompt input string."""

    return "\n".join(f"- {signal}" for signal in research_signals)


def _build_content_opportunity(
    *,
    request: GamingContentPipelineRequest,
    source_summary: str,
    opportunity_title: str,
    opportunity_reasoning: str,
    opportunity_score: int,
) -> ContentOpportunity:
    """Build a normalized content opportunity from typed research-stage outputs."""

    return ContentOpportunity(
        title=opportunity_title,
        game=request.game,
        topic=request.topic,
        source="supplied_research_signals",
        opportunity_score=float(opportunity_score),
        reasoning=opportunity_reasoning,
        estimated_duration_seconds=request.target_duration_seconds,
        references=list(request.research_signals) + [source_summary],
    )


class GamingContentPipeline:
    """Coordinate the first integrated AI content pipeline through existing application agents."""

    def __init__(
        self,
        *,
        research_agent: GamingResearchAgent,
        script_agent: GamingScriptAgent,
        storyboard_agent: GamingStoryboardAgent,
        media_agent: GamingMediaAgent,
        review_agent: GamingReviewAgent,
    ) -> None:
        self.research_agent = self._validate_dependency(
            research_agent,
            GamingResearchAgent,
            dependency_name="research_agent",
        )
        self.script_agent = self._validate_dependency(
            script_agent,
            GamingScriptAgent,
            dependency_name="script_agent",
        )
        self.storyboard_agent = self._validate_dependency(
            storyboard_agent,
            GamingStoryboardAgent,
            dependency_name="storyboard_agent",
        )
        self.media_agent = self._validate_dependency(
            media_agent,
            GamingMediaAgent,
            dependency_name="media_agent",
        )
        self.review_agent = self._validate_dependency(
            review_agent,
            GamingReviewAgent,
            dependency_name="review_agent",
        )
        self.logger = get_logger("orchestrator.content_pipeline")

    async def run(
        self,
        request: GamingContentPipelineRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingContentPipelineResult:
        """Run the first bounded happy-path AI content pipeline and stop at human review."""

        active_stage: str | None = None
        platform = request.platform.value
        serialized_research_signals = _serialize_research_signals(request.research_signals)

        self.logger.info(
            "content_pipeline_started",
            pipeline_name=PIPELINE_NAME,
        )

        try:
            active_stage = STAGE_TREND_DISCOVERY
            trend_discovery = await self.research_agent.discover_trends(
                GamingTrendDiscoveryRequest(
                    game=request.game,
                    topic=request.topic,
                    research_signals=serialized_research_signals,
                    platform=platform,
                    target_duration_seconds=request.target_duration_seconds,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_OPPORTUNITY_EVALUATION
            opportunity_evaluation = await self.research_agent.evaluate_opportunity(
                GamingOpportunityEvaluationRequest.from_trend_discovery(
                    trend_discovery,
                    platform=platform,
                    target_duration_seconds=request.target_duration_seconds,
                ),
                execution_options=execution_options,
            )

            opportunity = _build_content_opportunity(
                request=request,
                source_summary=trend_discovery.source_summary,
                opportunity_title=trend_discovery.title,
                opportunity_reasoning=opportunity_evaluation.reason,
                opportunity_score=opportunity_evaluation.score,
            )

            active_stage = STAGE_SCRIPT_GENERATION
            script = await self.script_agent.generate_script(
                GamingScriptGenerationRequest.from_research_outputs(
                    trend_discovery,
                    opportunity_evaluation,
                    platform=platform,
                    target_duration_seconds=request.target_duration_seconds,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_STORYBOARD_SCENE_BREAKDOWN
            storyboard = await self.storyboard_agent.break_down_scenes(
                GamingStoryboardSceneBreakdownRequest.from_script(
                    script,
                    game=request.game,
                    platform=platform,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_THUMBNAIL_CONCEPT
            thumbnail_concept = await self.media_agent.generate_thumbnail_concept(
                GamingThumbnailConceptRequest.from_storyboard(
                    storyboard,
                    game=request.game,
                    topic=request.topic,
                    angle=opportunity_evaluation.recommended_angle,
                    hook=script.hook,
                    platform=platform,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_NARRATION_DIRECTION
            narration_direction = await self.media_agent.generate_narration_direction(
                GamingNarrationDirectionRequest.from_script(
                    script,
                    game=request.game,
                    tone=request.tone,
                    platform=platform,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_SCRIPT_QUALITY_REVIEW
            script_quality = await self.review_agent.review_script_quality(
                GamingScriptQualityReviewRequest.from_script(
                    script,
                    game=request.game,
                    topic=request.topic,
                    angle=opportunity_evaluation.recommended_angle,
                    source_summary=trend_discovery.source_summary,
                    platform=platform,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_EVIDENCE_CONSISTENCY_REVIEW
            evidence_consistency = await self.review_agent.review_evidence_consistency(
                GamingEvidenceConsistencyReviewRequest.from_script(
                    script,
                    game=request.game,
                    source_summary=trend_discovery.source_summary,
                    research_notes=serialized_research_signals,
                    content_stage="script_draft",
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_STORYBOARD_QUALITY_REVIEW
            storyboard_quality = await self.review_agent.review_storyboard_quality(
                GamingStoryboardQualityReviewRequest.from_script_and_storyboard(
                    storyboard,
                    script,
                    game=request.game,
                    platform=platform,
                ),
                execution_options=execution_options,
            )

            active_stage = STAGE_PUBLICATION_READINESS_REVIEW
            publication_readiness = await self.review_agent.review_publication_readiness(
                GamingPublicationReadinessReviewRequest.from_review_inputs(
                    title=script.title,
                    game=request.game,
                    script_output=script,
                    storyboard_output=storyboard,
                    thumbnail_output=thumbnail_concept,
                    narration_output=narration_direction,
                    evidence_review_output=evidence_consistency,
                    platform=platform,
                ),
                execution_options=execution_options,
            )
        except CreatorOSError:
            self.logger.exception(
                "content_pipeline_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
            )
            raise
        except Exception as error:
            self.logger.exception(
                "content_pipeline_failed",
                pipeline_name=PIPELINE_NAME,
                stage=active_stage,
            )
            raise WorkflowError(
                "gaming content pipeline failed",
                code="gaming_content_pipeline_failed",
                details={"stage": active_stage},
            ) from error

        result = GamingContentPipelineResult(
            trend_discovery=trend_discovery,
            opportunity_evaluation=opportunity_evaluation,
            opportunity=opportunity,
            script=script,
            storyboard=storyboard,
            media_plans=GamingContentMediaPlanSet(
                thumbnail_concept=thumbnail_concept,
                narration_direction=narration_direction,
            ),
            review_results=GamingContentReviewSet(
                script_quality=script_quality,
                evidence_consistency=evidence_consistency,
                storyboard_quality=storyboard_quality,
            ),
            publication_readiness=publication_readiness,
        )

        self.logger.info(
            "content_pipeline_completed",
            pipeline_name=PIPELINE_NAME,
            final_stage=STAGE_PUBLICATION_READINESS_REVIEW,
        )
        return result

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


def build_gaming_content_pipeline(
    llm_execution_service: LLMExecutionService,
) -> GamingContentPipeline:
    """Build the integrated gaming content pipeline from one shared LLM execution service."""

    return GamingContentPipeline(
        research_agent=GamingResearchAgent(llm_execution_service),
        script_agent=GamingScriptAgent(llm_execution_service),
        storyboard_agent=GamingStoryboardAgent(llm_execution_service),
        media_agent=GamingMediaAgent(llm_execution_service),
        review_agent=GamingReviewAgent(llm_execution_service),
    )


__all__ = [
    "PIPELINE_NAME",
    "STAGE_EVIDENCE_CONSISTENCY_REVIEW",
    "STAGE_NARRATION_DIRECTION",
    "STAGE_OPPORTUNITY_EVALUATION",
    "STAGE_PUBLICATION_READINESS_REVIEW",
    "STAGE_SCRIPT_GENERATION",
    "STAGE_SCRIPT_QUALITY_REVIEW",
    "STAGE_STORYBOARD_QUALITY_REVIEW",
    "STAGE_STORYBOARD_SCENE_BREAKDOWN",
    "STAGE_THUMBNAIL_CONCEPT",
    "STAGE_TREND_DISCOVERY",
    "GamingContentPipeline",
    "build_gaming_content_pipeline",
]
