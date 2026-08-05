"""Unit tests for the CreatorOS prompt registry."""

from __future__ import annotations

import pytest

from creatoros.core import (
    PromptAlreadyRegisteredError,
    PromptNotFoundError,
)
from creatoros.prompts import (
    PromptDefinition,
    PromptMessage,
    PromptRole,
    PromptStatus,
    create_prompt_registry,
    get_prompt_registry,
)


def build_definition(
    *,
    name: str = "gaming_script",
    version: int = 1,
    status: PromptStatus = PromptStatus.ACTIVE,
) -> PromptDefinition:
    """Return a reusable prompt definition fixture."""

    return PromptDefinition(
        name=name,
        version=version,
        status=status,
        messages=[PromptMessage(role=PromptRole.USER, content=f"Prompt for {name} v{version}.")],
    )


@pytest.fixture(autouse=True)
def clear_cached_registry() -> None:
    """Reset the cached prompt registry between tests."""

    get_prompt_registry.cache_clear()


def test_registration_and_exact_retrieval_work() -> None:
    """Exact registration and retrieval should work by name and version."""

    registry = create_prompt_registry()
    definition = build_definition()
    registry.register(definition)

    assert registry.get("gaming_script", 1) == definition


def test_stored_definitions_are_copies() -> None:
    """Registry storage and retrieval should use detached copies."""

    registry = create_prompt_registry()
    definition = build_definition()
    registry.register(definition)
    definition.tags.append("mutated")
    resolved = registry.get("gaming_script", 1)
    resolved.tags.append("changed")

    assert registry.get("gaming_script", 1).tags == []


def test_duplicate_registration_is_rejected() -> None:
    """Duplicate name and version pairs should be rejected by default."""

    registry = create_prompt_registry()
    registry.register(build_definition())

    with pytest.raises(PromptAlreadyRegisteredError):
        registry.register(build_definition())


def test_replace_true_replaces_only_matching_version() -> None:
    """Replacement should only affect the matching prompt version."""

    registry = create_prompt_registry()
    registry.register(build_definition(version=1))
    registry.register(build_definition(version=2))
    replacement = build_definition(version=1)
    replacement.metadata["replacement"] = True

    registry.register(replacement, replace=True)

    assert registry.get("gaming_script", 1).metadata == {"replacement": True}
    assert registry.get("gaming_script", 2).metadata == {}


def test_unregister_returns_and_removes_a_prompt() -> None:
    """Unregister should return the removed definition and delete it."""

    registry = create_prompt_registry()
    registry.register(build_definition())

    removed = registry.unregister("gaming_script", 1)

    assert removed.name == "gaming_script"
    assert registry.contains("gaming_script", 1) is False


def test_missing_prompts_raise_prompt_not_found_error() -> None:
    """Missing prompt lookups should raise a typed not-found error."""

    registry = create_prompt_registry()

    with pytest.raises(PromptNotFoundError):
        registry.get("missing", 1)


def test_version_omission_returns_highest_active_version() -> None:
    """Default lookup should return the highest active version."""

    registry = create_prompt_registry()
    registry.register(build_definition(version=1, status=PromptStatus.ACTIVE))
    registry.register(build_definition(version=2, status=PromptStatus.ACTIVE))

    assert registry.get("gaming_script").version == 2


def test_draft_and_deprecated_versions_are_not_selected_as_default() -> None:
    """Default lookup should ignore non-active prompt versions."""

    registry = create_prompt_registry()
    registry.register(build_definition(version=1, status=PromptStatus.DRAFT))
    registry.register(build_definition(version=2, status=PromptStatus.DEPRECATED))

    with pytest.raises(PromptNotFoundError):
        registry.get("gaming_script")


def test_list_prompts_is_sorted_and_immutable() -> None:
    """Prompt listings should be predictably sorted and immutable."""

    registry = create_prompt_registry()
    registry.register(build_definition(name="zeta_prompt", version=2))
    registry.register(build_definition(name="alpha_prompt", version=1))

    prompts = registry.list_prompts()

    assert isinstance(prompts, tuple)
    assert [(prompt.name, prompt.version) for prompt in prompts] == [
        ("alpha_prompt", 1),
        ("zeta_prompt", 2),
    ]
    with pytest.raises(TypeError):
        prompts[0] = prompts[0]


def test_filtering_by_name_works() -> None:
    """Prompt listings should support filtering by prompt name."""

    registry = create_prompt_registry()
    registry.register(build_definition(name="alpha_prompt", version=1))
    registry.register(build_definition(name="beta_prompt", version=1))

    prompts = registry.list_prompts(name=" alpha_prompt ")

    assert len(prompts) == 1
    assert prompts[0].name == "alpha_prompt"


def test_filtering_by_status_works() -> None:
    """Prompt listings should support filtering by status."""

    registry = create_prompt_registry()
    registry.register(build_definition(version=1, status=PromptStatus.ACTIVE))
    registry.register(build_definition(version=2, status=PromptStatus.DRAFT))

    prompts = registry.list_prompts(status=PromptStatus.DRAFT)

    assert len(prompts) == 1
    assert prompts[0].status is PromptStatus.DRAFT


def test_clear_removes_all_entries() -> None:
    """Clearing the registry should remove all registered prompts."""

    registry = create_prompt_registry()
    registry.register(build_definition())

    registry.clear()

    assert registry.list_prompts() == ()


def test_fresh_registries_are_independent() -> None:
    """Fresh registry instances should not share state."""

    first = create_prompt_registry()
    second = create_prompt_registry()
    first.register(build_definition())

    assert second.list_prompts() == ()


def test_cached_registry_returns_the_same_instance() -> None:
    """The cached prompt registry helper should return one shared instance."""

    first = get_prompt_registry()
    second = get_prompt_registry()

    assert first is second
