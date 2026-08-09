"""Kling video provider shell exports for CreatorOS."""

from creatoros.providers.kling.bootstrap import register_kling_video_provider
from creatoros.providers.kling.transport import (
    DEFAULT_KLING_API_BASE_URL,
    DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH,
    DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL,
    DEFAULT_KLING_RESOLUTION_POLICY,
    DEFAULT_KLING_TASKS_ENDPOINT_PATH,
    KlingHTTPStatusTransportError,
    KlingHTTPVideoTransport,
)
from creatoros.providers.kling.video import (
    DEFAULT_KLING_VIDEO_MODEL,
    DEFAULT_KLING_VIDEO_PROVIDER_NAME,
    KlingAuthenticationTransportError,
    KlingDownloadedVideo,
    KlingMalformedResponseTransportError,
    KlingNetworkTransportError,
    KlingRateLimitTransportError,
    KlingTaskSnapshot,
    KlingTaskStatus,
    KlingTaskSubmission,
    KlingTransportError,
    KlingVideoProvider,
    KlingVideoTaskRequest,
)

__all__ = [
    "DEFAULT_KLING_API_BASE_URL",
    "DEFAULT_KLING_IMAGE_TO_VIDEO_ENDPOINT_PATH",
    "DEFAULT_KLING_IMAGE_TO_VIDEO_MODEL",
    "DEFAULT_KLING_RESOLUTION_POLICY",
    "DEFAULT_KLING_TASKS_ENDPOINT_PATH",
    "DEFAULT_KLING_VIDEO_MODEL",
    "DEFAULT_KLING_VIDEO_PROVIDER_NAME",
    "KlingAuthenticationTransportError",
    "KlingDownloadedVideo",
    "KlingHTTPStatusTransportError",
    "KlingHTTPVideoTransport",
    "KlingMalformedResponseTransportError",
    "KlingNetworkTransportError",
    "KlingRateLimitTransportError",
    "KlingTaskSnapshot",
    "KlingTaskStatus",
    "KlingTaskSubmission",
    "KlingTransportError",
    "KlingVideoProvider",
    "KlingVideoTaskRequest",
    "register_kling_video_provider",
]
