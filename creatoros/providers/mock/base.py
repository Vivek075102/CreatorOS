"""Shared deterministic base implementation for CreatorOS mock providers."""

from __future__ import annotations

from creatoros.providers.base import ProviderCapability, ProviderInfo


class MockProviderBase:
    """Provide shared deterministic behavior for mock providers."""

    def __init__(
        self,
        *,
        name: str,
        provider_type: str,
        capabilities: set[ProviderCapability],
        version: str = "1.0",
        is_healthy: bool = True,
    ) -> None:
        self._info = ProviderInfo(
            name=name,
            provider_type=provider_type,
            capabilities=set(capabilities),
            version=version,
        )
        self._is_healthy = is_healthy

    @property
    def info(self) -> ProviderInfo:
        """Return stable provider metadata for the mock provider."""

        return self._info.model_copy(deep=True)

    async def health_check(self) -> bool:
        """Return the configured health state without side effects."""

        return self._is_healthy


__all__ = ["MockProviderBase"]
