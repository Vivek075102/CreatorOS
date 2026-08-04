"""Domain enumerations for CreatorOS."""

from enum import StrEnum


class ContentPlatform(StrEnum):
    """Supported content publishing platforms."""

    YOUTUBE_SHORTS = "youtube_shorts"
    YOUTUBE_LONG_FORM = "youtube_long_form"
    INSTAGRAM_REELS = "instagram_reels"
    TIKTOK = "tiktok"
    FACEBOOK_REELS = "facebook_reels"
    X = "x"


class ContentStatus(StrEnum):
    """High-level content lifecycle states."""

    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    """Workflow lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(StrEnum):
    """Workflow step lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    """Approval states for reviewable workflow outputs."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AssetType(StrEnum):
    """Asset categories used by CreatorOS workflows."""

    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    NARRATION = "narration"
    MUSIC = "music"
    CAPTION = "caption"
    THUMBNAIL = "thumbnail"
    DOCUMENT = "document"
