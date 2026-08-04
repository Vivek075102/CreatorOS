"""Unit tests for CreatorOS domain enumerations."""

from pydantic import BaseModel, ConfigDict

from creatoros.domain.enums import (
    ApprovalStatus,
    AssetType,
    ContentPlatform,
    ContentStatus,
    WorkflowStatus,
    WorkflowStepStatus,
)


def test_enums_have_expected_exact_string_values() -> None:
    """All requested enums should expose the exact expected values."""

    assert [member.value for member in ContentPlatform] == [
        "youtube_shorts",
        "youtube_long_form",
        "instagram_reels",
        "tiktok",
        "facebook_reels",
        "x",
    ]
    assert [member.value for member in ContentStatus] == [
        "draft",
        "awaiting_approval",
        "approved",
        "rejected",
        "processing",
        "completed",
        "failed",
        "cancelled",
    ]
    assert [member.value for member in WorkflowStatus] == [
        "pending",
        "running",
        "paused",
        "awaiting_approval",
        "completed",
        "failed",
        "cancelled",
    ]
    assert [member.value for member in WorkflowStepStatus] == [
        "pending",
        "running",
        "awaiting_approval",
        "completed",
        "failed",
        "skipped",
        "cancelled",
    ]
    assert [member.value for member in ApprovalStatus] == [
        "not_required",
        "pending",
        "approved",
        "rejected",
    ]
    assert [member.value for member in AssetType] == [
        "video",
        "image",
        "audio",
        "narration",
        "music",
        "caption",
        "thumbnail",
        "document",
    ]


class EnumContainer(BaseModel):
    """Minimal Pydantic model used to verify enum serialization behavior."""

    model_config = ConfigDict(use_enum_values=True)

    platform: ContentPlatform
    status: WorkflowStatus


def test_enums_serialize_predictably_through_pydantic_models() -> None:
    """Enum values should serialize to their expected string representations."""

    container = EnumContainer(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        status=WorkflowStatus.RUNNING,
    )

    assert container.model_dump() == {
        "platform": "youtube_shorts",
        "status": "running",
    }
