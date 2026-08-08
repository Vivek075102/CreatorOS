"""Tests for the first builtin gaming research prompt assets."""

from __future__ import annotations

import json
from pathlib import Path

from creatoros.prompts import PromptAssetCategory, PromptDefinition, PromptLoader, PromptStatus

RESEARCH_PROMPT_PATHS = [
    Path("research/gaming/gaming_discover_trends.v1.json"),
    Path("research/gaming/gaming_evaluate_opportunity.v1.json"),
    Path("research/gaming/gaming_expand_keywords.v1.json"),
]


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_exactly_three_research_gaming_prompt_json_files_exist() -> None:
    """The repository should contain exactly the three builtin gaming research prompts."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(
        path.relative_to(prompts_root)
        for path in prompts_root.rglob("*.json")
        if path.name != "manifest.json"
    )

    assert json_paths == sorted(RESEARCH_PROMPT_PATHS)


def test_all_three_load_as_prompt_definitions() -> None:
    """Each builtin research prompt asset should load as a PromptDefinition."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    loaded = [loader.load_file(path) for path in RESEARCH_PROMPT_PATHS]

    assert all(isinstance(definition, PromptDefinition) for definition in loaded)


def test_all_three_are_active_and_version_one() -> None:
    """Builtin research prompts should be active version-one assets."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    definitions = [loader.load_file(path) for path in RESEARCH_PROMPT_PATHS]

    assert [definition.status for definition in definitions] == [PromptStatus.ACTIVE] * 3
    assert [definition.version for definition in definitions] == [1, 1, 1]


def test_all_names_match_filenames_and_belong_to_research_category() -> None:
    """Builtin prompt names should match filenames and live under research."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    for relative_path in RESEARCH_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.name == relative_path.name.split(".v", 1)[0]
        assert relative_path.parts[0] == PromptAssetCategory.RESEARCH.value


def test_required_metadata_marks_gaming_research_domain() -> None:
    """Builtin research prompts should carry the expected metadata contract."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    for relative_path in RESEARCH_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.metadata["domain"] == "gaming"
        assert definition.metadata["stage"] == "research"
        assert definition.metadata["owner"] == "creatoros"
        assert definition.metadata["provider_independent"] is True


def test_no_provider_vendor_names_urls_or_credentials_appear_in_prompt_assets() -> None:
    """Research prompt assets should stay provider-independent and safe."""

    prompts_root = _repo_prompts_dir()
    combined_contents = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in RESEARCH_PROMPT_PATHS)
    normalized = combined_contents.casefold()

    for forbidden in ["openai", "anthropic", "gemini", "ollama", "api_key", "http://", "https://", "token"]:
        assert forbidden not in normalized


def test_no_prompt_claims_live_browsing_or_internet_access() -> None:
    """Research prompt assets should not pretend they can browse live data."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in RESEARCH_PROMPT_PATHS).casefold()

    assert "live internet access" in normalized
    assert "browsing capability" not in normalized
    assert "browse the web" not in normalized
    assert "current search results" not in normalized


def test_required_variables_match_specification() -> None:
    """Research prompt variables should match the documented contracts."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    discover = loader.load_file(RESEARCH_PROMPT_PATHS[0])
    evaluate = loader.load_file(RESEARCH_PROMPT_PATHS[1])
    expand = loader.load_file(RESEARCH_PROMPT_PATHS[2])

    assert [variable.name for variable in discover.variables] == [
        "game",
        "topic",
        "research_signals",
        "platform",
        "target_duration_seconds",
    ]
    assert [variable.name for variable in evaluate.variables] == [
        "game",
        "title",
        "topic",
        "angle",
        "source_summary",
        "platform",
        "target_duration_seconds",
    ]
    assert [variable.name for variable in expand.variables] == [
        "game",
        "topic",
        "seed_keywords",
        "platform",
    ]


def test_prompt_contents_contain_required_output_labels() -> None:
    """Research prompt bodies should contain the required output labels."""

    prompts_root = _repo_prompts_dir()
    discover_payload = json.loads((prompts_root / RESEARCH_PROMPT_PATHS[0]).read_text(encoding="utf-8"))
    evaluate_payload = json.loads((prompts_root / RESEARCH_PROMPT_PATHS[1]).read_text(encoding="utf-8"))
    expand_payload = json.loads((prompts_root / RESEARCH_PROMPT_PATHS[2]).read_text(encoding="utf-8"))

    discover_content = "\n".join(message["content"] for message in discover_payload["messages"])
    evaluate_content = "\n".join(message["content"] for message in evaluate_payload["messages"])
    expand_content = "\n".join(message["content"] for message in expand_payload["messages"])

    for label in ["TITLE:", "GAME:", "TOPIC:", "ANGLE:", "WHY_NOW:", "SOURCE_SUMMARY:", "CONFIDENCE:"]:
        assert label in discover_content
    for label in ["DECISION:", "SCORE:", "STRENGTHS:", "RISKS:", "RECOMMENDED_ANGLE:", "HOOK_DIRECTION:", "REASON:"]:
        assert label in evaluate_content
    for label in ["PRIMARY:", "RELATED:", "QUESTIONS:", "ENTITIES:"]:
        assert label in expand_content


def test_prompt_assets_serialize_and_restore_predictably() -> None:
    """Builtin research prompt definitions should round-trip predictably."""

    prompts_root = _repo_prompts_dir()
    loader = PromptLoader(base_dir=prompts_root)

    for relative_path in RESEARCH_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        restored = PromptDefinition.model_validate(definition.model_dump(mode="python"))
        assert restored == definition
