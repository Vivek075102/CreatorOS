"""Bootstrap helpers for the CreatorOS Kling video provider shell."""

from __future__ import annotations

from creatoros.config import get_settings
from creatoros.providers.kling.transport import KlingHTTPVideoTransport
from creatoros.providers.kling.video import KlingVideoProvider, _KlingVideoTransport
from creatoros.providers.registry import ProviderRegistry


def register_kling_video_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    api_key: str | None = None,
    transport: _KlingVideoTransport | None = None,
    default_model: str | None = None,
) -> KlingVideoProvider:
    """Register one Kling video provider without making any network requests."""

    settings = get_settings()
    resolved_transport = transport
    if resolved_transport is None:
        resolved_transport = KlingHTTPVideoTransport(base_url=settings.kling_api_base_url)

    provider = KlingVideoProvider(
        api_key=settings.kling_api_key if api_key is None else api_key,
        transport=resolved_transport,
        default_model=settings.default_video_model if default_model is None else default_model,
        timeout_seconds=settings.kling_video_timeout_seconds,
        poll_interval_seconds=settings.kling_video_poll_interval_seconds,
    )
    registry.register(provider, replace=replace)
    return provider


__all__ = ["register_kling_video_provider"]
