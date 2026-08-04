"""Focused demo agents for the first executable CreatorOS gaming workflow."""

from __future__ import annotations

from creatoros.agents import AgentExecutionContext, BaseAgent
from creatoros.core import CreatorOSValidationError
from creatoros.domain import (
    AssetType,
    ContentBrief,
    ContentOpportunity,
    PublishedPost,
    PublishingPackage,
    Scene,
    Script,
    Storyboard,
)
from creatoros.orchestrator.models import DemoAssetBundle, GamingWorkflowInput
from creatoros.providers import (
    ImageProvider,
    LLMProvider,
    PublishingProvider,
    TrendProvider,
    VideoProvider,
    VoiceProvider,
)


def _format_opportunity_title(
    *,
    game: str,
    topic: str,
) -> str:
    """Build a deterministic, readable opportunity title from workflow input."""

    normalized_game = game.strip()
    normalized_topic = " ".join(topic.strip().split()).title()
    return f"{normalized_game}: {normalized_topic}"


class DemoResearchAgent(BaseAgent[GamingWorkflowInput, ContentOpportunity]):
    """Normalize mock trend data into a typed content opportunity."""

    @property
    def name(self) -> str:
        return "demo_research_agent"

    async def execute(
        self,
        input_data: GamingWorkflowInput,
        *,
        context: AgentExecutionContext,
    ) -> ContentOpportunity:
        provider = self.get_provider("trend", "mock")
        if not isinstance(provider, TrendProvider):
            raise CreatorOSValidationError(
                "registered trend provider does not satisfy TrendProvider",
                code="demo_invalid_provider",
                details={"provider_type": "trend", "provider_name": "mock"},
            )

        query = f"{input_data.game} {input_data.topic}"
        result = await provider.research_trends(query)
        if not result.data:
            raise CreatorOSValidationError(
                "no trend records were returned",
                code="demo_no_trend_records",
                details={"provider_name": "mock"},
            )

        record = result.data[0]
        title = _format_opportunity_title(
            game=input_data.game,
            topic=input_data.topic,
        )
        game = input_data.game
        topic = input_data.topic
        source = str(record.get("source") or "mock_trends")
        raw_score = record.get("score")
        score = float(raw_score) if isinstance(raw_score, int | float | str) else 75.0
        reasoning = str(record.get("reasoning") or "Deterministic mock trend selected for demo workflow.")
        raw_duration = record.get("estimated_duration_seconds")
        duration = int(raw_duration) if isinstance(raw_duration, int | float | str) else 30
        references_value = record.get("references")
        references = (
            [str(item) for item in references_value]
            if isinstance(references_value, list)
            else []
        )

        return ContentOpportunity(
            title=title,
            game=game,
            topic=topic,
            source=source,
            opportunity_score=score,
            reasoning=reasoning,
            estimated_duration_seconds=duration,
            references=references,
        )


class DemoScriptAgent(BaseAgent[ContentBrief, Script]):
    """Generate a deterministic typed script from a content brief."""

    @property
    def name(self) -> str:
        return "demo_script_agent"

    async def execute(
        self,
        input_data: ContentBrief,
        *,
        context: AgentExecutionContext,
    ) -> Script:
        provider = self.get_provider("llm", "mock")
        if not isinstance(provider, LLMProvider):
            raise CreatorOSValidationError(
                "registered llm provider does not satisfy LLMProvider",
                code="demo_invalid_provider",
                details={"provider_type": "llm", "provider_name": "mock"},
            )

        prompt = (
            f"Create a concise {input_data.platform.value} script body about "
            f"{input_data.title} for {input_data.audience}."
        )
        result = await provider.generate_text(prompt)
        return Script(
            title=input_data.title,
            hook=f"{input_data.hook_direction}: {input_data.title}",
            body=result.data,
            ending="That is the quick breakdown for this gaming fact.",
            call_to_action="Follow CreatorOS for more gaming shorts.",
            estimated_duration_seconds=30,
            version=1,
        )


class DemoStoryboardAgent(BaseAgent[Script, Storyboard]):
    """Create a deterministic storyboard without calling additional engines."""

    @property
    def name(self) -> str:
        return "demo_storyboard_agent"

    async def execute(
        self,
        input_data: Script,
        *,
        context: AgentExecutionContext,
    ) -> Storyboard:
        total_duration = input_data.estimated_duration_seconds
        first_duration = max(1, total_duration // 3)
        second_duration = max(1, total_duration // 2)
        third_duration = max(1, total_duration - first_duration - second_duration)

        scenes = [
            Scene(
                scene_number=1,
                duration_seconds=first_duration,
                narration=input_data.hook,
                visual_description="Fast hook scene with bold on-screen gaming fact text.",
                asset_notes="Use a dynamic gameplay opener.",
            ),
            Scene(
                scene_number=2,
                duration_seconds=second_duration,
                narration=input_data.body,
                visual_description="Main content scene showing the core gaming explanation.",
                asset_notes="Overlay concise supporting captions.",
            ),
            Scene(
                scene_number=3,
                duration_seconds=third_duration,
                narration=f"{input_data.ending} {input_data.call_to_action}",
                visual_description="Ending scene with call to action and clean close.",
                asset_notes="End with channel branding frame.",
            ),
        ]

        return Storyboard(
            title=f"{input_data.title} storyboard",
            scenes=scenes,
            notes="Deterministic demo storyboard generated locally.",
        )


class DemoAssetAgent(BaseAgent[Storyboard, DemoAssetBundle]):
    """Generate deterministic mock media assets from a storyboard."""

    @property
    def name(self) -> str:
        return "demo_asset_agent"

    async def execute(
        self,
        input_data: Storyboard,
        *,
        context: AgentExecutionContext,
    ) -> DemoAssetBundle:
        video_provider = self.get_provider("video", "mock")
        image_provider = self.get_provider("image", "mock")
        voice_provider = self.get_provider("voice", "mock")

        if not isinstance(video_provider, VideoProvider):
            raise CreatorOSValidationError(
                "registered video provider does not satisfy VideoProvider",
                code="demo_invalid_provider",
                details={"provider_type": "video", "provider_name": "mock"},
            )
        if not isinstance(image_provider, ImageProvider):
            raise CreatorOSValidationError(
                "registered image provider does not satisfy ImageProvider",
                code="demo_invalid_provider",
                details={"provider_type": "image", "provider_name": "mock"},
            )
        if not isinstance(voice_provider, VoiceProvider):
            raise CreatorOSValidationError(
                "registered voice provider does not satisfy VoiceProvider",
                code="demo_invalid_provider",
                details={"provider_type": "voice", "provider_name": "mock"},
            )

        video_result = await video_provider.generate_video(f"Storyboard video for {input_data.title}")
        thumbnail_result = await image_provider.generate_image(f"Thumbnail for {input_data.title}")
        narration_text = " ".join(scene.narration for scene in input_data.scenes)
        narration_result = await voice_provider.generate_voice(narration_text)

        video = video_result.data.model_copy(
            update={"metadata": {"role": "video", "storyboard_id": input_data.id}},
            deep=True,
        )
        thumbnail = thumbnail_result.data.model_copy(
            update={"asset_type": AssetType.THUMBNAIL, "metadata": {"role": "thumbnail", "storyboard_id": input_data.id}},
            deep=True,
        )
        narration = narration_result.data.model_copy(
            update={"metadata": {"role": "narration", "storyboard_id": input_data.id}},
            deep=True,
        )

        return DemoAssetBundle(video=video, thumbnail=thumbnail, narration=narration)


class DemoPublishingAgent(BaseAgent[PublishingPackage, PublishedPost]):
    """Publish a deterministic demo package through the mock publishing provider."""

    @property
    def name(self) -> str:
        return "demo_publishing_agent"

    async def execute(
        self,
        input_data: PublishingPackage,
        *,
        context: AgentExecutionContext,
    ) -> PublishedPost:
        provider = self.get_provider("publishing", "mock")
        if not isinstance(provider, PublishingProvider):
            raise CreatorOSValidationError(
                "registered publishing provider does not satisfy PublishingProvider",
                code="demo_invalid_provider",
                details={"provider_type": "publishing", "provider_name": "mock"},
            )

        result = await provider.publish(input_data)
        return result.data


__all__ = [
    "DemoAssetAgent",
    "DemoPublishingAgent",
    "DemoResearchAgent",
    "DemoScriptAgent",
    "DemoStoryboardAgent",
]
