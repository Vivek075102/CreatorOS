"""Application-layer service for provider-independent Short composition."""

from __future__ import annotations

from creatoros.config import Settings, get_settings
from creatoros.core import ProviderTypeMismatchError
from creatoros.providers import (
    ProviderRegistry,
    ProviderRequestContext,
    ProviderResult,
    RenderedVideo,
    RenderProvider,
    ShortRenderRequest,
)
from creatoros.providers.mock import create_mock_render_provider_registry


class MediaRenderService:
    """Resolve a render provider and execute a composition request."""

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        settings: Settings,
    ) -> None:
        self.provider_registry = provider_registry
        self.settings = settings

    async def render(
        self,
        request: ShortRenderRequest,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[RenderedVideo]:
        """Render one provider-neutral Short request through a resolved render provider."""

        provider = self._resolve_provider(provider_name)
        return await provider.render(request, context=context)

    def _resolve_provider(self, provider_name: str | None) -> RenderProvider:
        """Resolve either an explicit or configured default render provider."""

        if provider_name is None:
            provider_name = self.settings.default_render_provider

        provider = self.provider_registry.get("render", provider_name)
        if not isinstance(provider, RenderProvider):
            raise ProviderTypeMismatchError("render", provider_name.strip().lower(), "RenderProvider")
        return provider


def create_media_render_service(
    *,
    provider_registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
) -> MediaRenderService:
    """Create a safe default render service using the deterministic mock provider."""

    resolved_settings = get_settings() if settings is None else settings
    resolved_provider_registry = (
        create_mock_render_provider_registry()
        if provider_registry is None
        else provider_registry
    )
    return MediaRenderService(resolved_provider_registry, resolved_settings)


__all__ = [
    "MediaRenderService",
    "create_media_render_service",
]
