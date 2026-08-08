"""Unit tests for the CreatorOS provider registry."""

from __future__ import annotations

import pytest

from creatoros.core import (
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
    ProviderRegistryError,
    ProviderTypeMismatchError,
)
from creatoros.providers import (
    LLMCapabilities,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderCapability,
    ProviderInfo,
    create_provider_registry,
    get_provider_registry,
    resolve_default_llm_provider,
)


def build_provider_info(
    *,
    name: str,
    provider_type: str,
    capability: ProviderCapability,
) -> ProviderInfo:
    """Create provider metadata for registry tests."""

    return ProviderInfo(
        name=name,
        provider_type=provider_type,
        capabilities={capability},
    )


class FakeLLMProvider:
    """Minimal fake LLM provider used for registry behavior tests."""

    def __init__(self, *, name: str, provider_type: str = "llm") -> None:
        self._info = build_provider_info(
            name=name,
            provider_type=provider_type,
            capability=ProviderCapability.TEXT_GENERATION,
        )
        self.health_check_calls = 0

    @property
    def info(self) -> ProviderInfo:
        return self._info

    @property
    def llm_capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_temperature=True,
            supports_max_output_tokens=True,
            supports_system_messages=True,
            supports_structured_text=True,
        )

    async def health_check(self) -> bool:
        self.health_check_calls += 1
        return True

    async def generate(self, request: LLMRequest, *, context=None) -> LLMResponse:
        return LLMResponse(
            text=request.messages[0].content,
            provider_name=self._info.name,
            model=request.model,
        )

    async def generate_text(self, prompt: str, *, context=None):
        raise NotImplementedError

    async def generate_structured(self, prompt: str, *, response_model, context=None):
        raise NotImplementedError


class FakeSearchProvider:
    """Minimal fake search provider used for registry behavior tests."""

    def __init__(self, *, name: str, provider_type: str = "search") -> None:
        self._info = build_provider_info(
            name=name,
            provider_type=provider_type,
            capability=ProviderCapability.WEB_SEARCH,
        )

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def health_check(self) -> bool:
        return True

    async def search(self, query: str, *, limit: int = 10, context=None):
        raise NotImplementedError


class NotAProvider:
    """Object that intentionally does not satisfy the Provider protocol."""


@pytest.fixture(autouse=True)
def clear_cached_registry() -> None:
    """Reset the cached application registry between tests."""

    get_provider_registry.cache_clear()


def test_valid_provider_can_be_registered() -> None:
    """A valid provider should register successfully."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")

    registry.register(provider)

    assert registry.contains("llm", "openai")


def test_registered_providers_can_be_retrieved() -> None:
    """Registered providers should be retrievable by type and name."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")
    registry.register(provider)

    assert registry.get("llm", "openai") is provider


def test_registration_normalizes_provider_names_and_types() -> None:
    """Registration and lookup should normalize provider identifiers."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name=" OpenAI ", provider_type=" LLM ")
    registry.register(provider)

    assert registry.contains("llm", "openai")
    assert registry.get("LLM", " OPENAI ") is provider


def test_duplicate_registration_is_rejected_by_default() -> None:
    """Duplicate provider registrations should fail unless replacement is requested."""

    registry = create_provider_registry()
    registry.register(FakeLLMProvider(name="OpenAI"))

    with pytest.raises(ProviderAlreadyRegisteredError):
        registry.register(FakeLLMProvider(name="OpenAI"))


def test_duplicate_registration_can_be_replaced_explicitly() -> None:
    """Duplicate registrations should be replaceable when requested explicitly."""

    registry = create_provider_registry()
    first = FakeLLMProvider(name="OpenAI")
    second = FakeLLMProvider(name="OpenAI")
    registry.register(first)

    registry.register(second, replace=True)

    assert registry.get("llm", "openai") is second


def test_unregister_removes_and_returns_provider() -> None:
    """Unregister should remove and return the matching provider."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")
    registry.register(provider)

    removed = registry.unregister("llm", "openai")

    assert removed is provider
    assert not registry.contains("llm", "openai")


def test_unregister_raises_not_found_when_absent() -> None:
    """Unregister should raise a typed error when the provider is absent."""

    registry = create_provider_registry()

    with pytest.raises(ProviderNotFoundError):
        registry.unregister("llm", "missing")


def test_get_raises_not_found_when_absent() -> None:
    """Get should raise a typed error when the provider is absent."""

    registry = create_provider_registry()

    with pytest.raises(ProviderNotFoundError):
        registry.get("llm", "missing")


def test_contains_returns_correct_values() -> None:
    """Contains should report whether a registration exists."""

    registry = create_provider_registry()
    registry.register(FakeLLMProvider(name="OpenAI"))

    assert registry.contains("llm", "openai") is True
    assert registry.contains("llm", "missing") is False


def test_list_providers_returns_immutable_tuple_metadata() -> None:
    """List results should be immutable ProviderInfo metadata."""

    registry = create_provider_registry()
    registry.register(FakeLLMProvider(name="OpenAI"))

    providers = registry.list_providers()

    assert isinstance(providers, tuple)
    assert providers[0].name == "OpenAI"
    with pytest.raises(TypeError):
        providers[0] = providers[0]


def test_list_providers_is_predictably_sorted() -> None:
    """List results should be sorted by provider type and name."""

    registry = create_provider_registry()
    registry.register(FakeSearchProvider(name="Brave", provider_type="search"))
    registry.register(FakeLLMProvider(name="Zeta", provider_type="llm"))
    registry.register(FakeLLMProvider(name="Alpha", provider_type="llm"))

    providers = registry.list_providers()

    assert [(provider.provider_type, provider.name) for provider in providers] == [
        ("llm", "Alpha"),
        ("llm", "Zeta"),
        ("search", "Brave"),
    ]


def test_list_providers_can_filter_by_provider_type() -> None:
    """List results should support filtering by provider type."""

    registry = create_provider_registry()
    registry.register(FakeLLMProvider(name="Alpha"))
    registry.register(FakeSearchProvider(name="Brave"))

    providers = registry.list_providers("llm")

    assert len(providers) == 1
    assert providers[0].provider_type == "llm"
    assert providers[0].name == "Alpha"


def test_clear_removes_all_registrations() -> None:
    """Clear should remove every registered provider."""

    registry = create_provider_registry()
    registry.register(FakeLLMProvider(name="Alpha"))
    registry.register(FakeSearchProvider(name="Brave"))

    registry.clear()

    assert registry.list_providers() == ()


def test_invalid_non_provider_objects_are_rejected() -> None:
    """Register should reject objects that do not satisfy the Provider protocol."""

    registry = create_provider_registry()

    with pytest.raises(ProviderRegistryError):
        registry.register(NotAProvider())  # type: ignore[arg-type]


def test_blank_names_or_provider_types_are_rejected() -> None:
    """Blank registry identifiers should raise typed errors."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")
    registry.register(provider)

    with pytest.raises(ProviderRegistryError):
        registry.get("   ", "openai")

    with pytest.raises(ProviderRegistryError):
        registry.get("llm", "   ")


def test_get_typed_returns_a_correctly_typed_provider() -> None:
    """Typed lookup should return providers with the expected contract."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")
    registry.register(provider)

    resolved = registry.get_typed("llm", "openai", LLMProvider)

    assert resolved is provider


def test_get_typed_raises_type_mismatch_for_wrong_contract() -> None:
    """Typed lookup should raise a typed error for contract mismatches."""

    registry = create_provider_registry()
    registry.register(FakeSearchProvider(name="Brave", provider_type="search"))

    with pytest.raises(ProviderTypeMismatchError):
        registry.get_typed("search", "brave", LLMProvider)


def test_create_provider_registry_returns_independent_registries() -> None:
    """Factory-created registries should not share state."""

    first = create_provider_registry()
    second = create_provider_registry()
    first.register(FakeLLMProvider(name="OpenAI"))

    assert first is not second
    assert second.list_providers() == ()


def test_get_provider_registry_returns_same_cached_registry() -> None:
    """The cached registry helper should return a single shared instance."""

    first = get_provider_registry()
    second = get_provider_registry()

    assert first is second


def test_resolve_default_llm_provider_uses_settings_and_returns_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default LLM resolution should respect the configured provider name."""

    class StubSettings:
        default_llm_provider = "anthropic"

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="Anthropic")
    registry.register(provider)
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    resolved = resolve_default_llm_provider(registry)

    assert resolved is provider


def test_resolve_default_llm_provider_raises_typed_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default LLM resolution should raise a typed error when configuration points to nothing."""

    class StubSettings:
        default_llm_provider = "missing"

    registry = create_provider_registry()
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: StubSettings())

    with pytest.raises(ProviderNotFoundError):
        resolve_default_llm_provider(registry)


def test_error_details_contain_only_safe_provider_identifiers() -> None:
    """Registry errors should expose only safe provider identifiers in details."""

    registry = create_provider_registry()

    with pytest.raises(ProviderNotFoundError) as exc_info:
        registry.get("llm", "missing")

    assert exc_info.value.details == {
        "provider_type": "llm",
        "provider_name": "missing",
    }


def test_registration_does_not_call_health_check() -> None:
    """Registration should not call provider health checks."""

    registry = create_provider_registry()
    provider = FakeLLMProvider(name="OpenAI")

    registry.register(provider)

    assert provider.health_check_calls == 0


def test_replacing_one_provider_does_not_affect_other_registrations() -> None:
    """Replacing a registration should not change unrelated provider entries."""

    registry = create_provider_registry()
    first_llm = FakeLLMProvider(name="OpenAI")
    second_llm = FakeLLMProvider(name="OpenAI")
    search = FakeSearchProvider(name="Brave")
    registry.register(first_llm)
    registry.register(search)

    registry.register(second_llm, replace=True)

    assert registry.get("llm", "openai") is second_llm
    assert registry.get("search", "brave") is search
