"""Tests for builtin prompt bootstrap helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from creatoros.core import CreatorOSValidationError, PromptAlreadyRegisteredError, PromptLoadError
from creatoros.prompts import (
    GAMING_CTA,
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EXPAND_KEYWORDS,
    GAMING_HOOK,
    YOUTUBE_SHORTS_SCRIPT,
    create_builtin_prompt_registry,
    create_prompt_registry,
    get_prompt_registry,
    load_builtin_prompts,
)


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_load_builtin_prompts_registers_all_six_definitions() -> None:
    """Builtin bootstrap loading should register all research and script prompts."""

    registry = create_prompt_registry()

    loaded = load_builtin_prompts(registry, base_dir=_repo_prompts_dir())

    assert sorted(definition.name for definition in loaded) == [
        GAMING_CTA,
        GAMING_DISCOVER_TRENDS,
        GAMING_EVALUATE_OPPORTUNITY,
        GAMING_EXPAND_KEYWORDS,
        GAMING_HOOK,
        YOUTUBE_SHORTS_SCRIPT,
    ]
    assert registry.contains(GAMING_CTA, 1) is True
    assert registry.contains(GAMING_DISCOVER_TRENDS, 1) is True
    assert registry.contains(GAMING_EVALUATE_OPPORTUNITY, 1) is True
    assert registry.contains(GAMING_EXPAND_KEYWORDS, 1) is True
    assert registry.contains(GAMING_HOOK, 1) is True
    assert registry.contains(YOUTUBE_SHORTS_SCRIPT, 1) is True


def test_fresh_builtin_registry_contains_all_six_prompts() -> None:
    """Creating a builtin registry should populate a fresh registry only."""

    registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())

    assert [definition.name for definition in registry.list_prompts()] == [
        GAMING_CTA,
        GAMING_DISCOVER_TRENDS,
        GAMING_EVALUATE_OPPORTUNITY,
        GAMING_EXPAND_KEYWORDS,
        GAMING_HOOK,
        YOUTUBE_SHORTS_SCRIPT,
    ]


def test_existing_research_prompts_remain_available_after_script_addition() -> None:
    """Adding builtin script prompts should not affect research prompt availability."""

    registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())

    assert registry.get(GAMING_DISCOVER_TRENDS).name == GAMING_DISCOVER_TRENDS
    assert registry.get(GAMING_EVALUATE_OPPORTUNITY).name == GAMING_EVALUATE_OPPORTUNITY
    assert registry.get(GAMING_EXPAND_KEYWORDS).name == GAMING_EXPAND_KEYWORDS


def test_script_prompts_are_retrievable_by_stable_logical_name() -> None:
    """Builtin script prompts should resolve by their stable logical names."""

    registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())

    assert registry.get(YOUTUBE_SHORTS_SCRIPT).name == YOUTUBE_SHORTS_SCRIPT
    assert registry.get(GAMING_HOOK).name == GAMING_HOOK
    assert registry.get(GAMING_CTA).name == GAMING_CTA


def test_cached_global_registry_is_not_modified() -> None:
    """Builtin bootstrap should not mutate the cached global registry implicitly."""

    get_prompt_registry.cache_clear()
    global_registry = get_prompt_registry()

    assert global_registry.list_prompts() == ()

    create_builtin_prompt_registry(base_dir=_repo_prompts_dir())

    assert global_registry.list_prompts() == ()


def test_duplicate_loading_fails_when_replace_false() -> None:
    """Loading builtin prompts twice without replacement should fail."""

    registry = create_prompt_registry()
    load_builtin_prompts(registry, base_dir=_repo_prompts_dir())

    with pytest.raises(PromptAlreadyRegisteredError):
        load_builtin_prompts(registry, base_dir=_repo_prompts_dir(), replace=False)


def test_replace_true_succeeds() -> None:
    """Builtin prompt loading should honor explicit replacement."""

    registry = create_prompt_registry()
    load_builtin_prompts(registry, base_dir=_repo_prompts_dir())

    loaded = load_builtin_prompts(registry, base_dir=_repo_prompts_dir(), replace=True)

    assert len(loaded) == 6


def test_returned_definitions_are_copies() -> None:
    """Bootstrap helpers should return detached prompt definition copies."""

    registry = create_prompt_registry()
    loaded = load_builtin_prompts(registry, base_dir=_repo_prompts_dir())

    loaded[0].tags.append("mutated")

    assert "mutated" not in registry.get(GAMING_DISCOVER_TRENDS, 1).tags


def test_missing_or_invalid_manifest_fails_safely(tmp_path: Path) -> None:
    """Missing or invalid manifests should fail without exposing contents."""

    registry = create_prompt_registry()

    with pytest.raises(PromptLoadError):
        load_builtin_prompts(registry, base_dir=tmp_path)

    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "entries": [], "metadata": {"description": "SECRET"}}),
        encoding="utf-8",
    )
    with pytest.raises(CreatorOSValidationError) as exc_info:
        load_builtin_prompts(registry, base_dir=tmp_path)

    assert "SECRET" not in str(exc_info.value)
