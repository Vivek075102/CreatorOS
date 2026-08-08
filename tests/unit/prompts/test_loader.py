"""Unit tests for filesystem prompt loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from creatoros.core import CreatorOSValidationError, PromptAlreadyRegisteredError, PromptLoadError
from creatoros.prompts import PromptLoader, PromptStatus, create_prompt_registry


def write_prompt_file(
    path: Path,
    *,
    name: str = "gaming_script",
    version: int = 1,
    status: str = "active",
    messages: list[dict[str, object]] | None = None,
    variables: list[dict[str, object]] | None = None,
) -> None:
    """Write a valid JSON prompt definition file."""

    payload = {
        "name": name,
        "version": version,
        "status": status,
        "description": "Generate a script.",
        "format": "text",
        "messages": messages
        or [
            {"role": "system", "content": "You create concise gaming content."},
            {"role": "user", "content": "Create a script about {game} and {topic}."},
        ],
        "variables": variables
        or [
            {"name": "game", "variable_type": "string", "required": True},
            {"name": "topic", "variable_type": "string", "required": True},
        ],
        "tags": ["gaming", "script"],
        "metadata": {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_json_file_loads_successfully(tmp_path: Path) -> None:
    """A valid JSON prompt file should load successfully."""

    prompt_path = tmp_path / "gaming_script.json"
    write_prompt_file(prompt_path)
    loader = PromptLoader(base_dir=tmp_path)

    definition = loader.load_file(prompt_path)

    assert definition.name == "gaming_script"
    assert definition.status is PromptStatus.ACTIVE


def test_relative_file_paths_resolve_under_base_dir(tmp_path: Path) -> None:
    """Relative file paths should resolve under the configured base directory."""

    prompt_path = tmp_path / "nested" / "gaming_script.json"
    write_prompt_file(prompt_path)
    loader = PromptLoader(base_dir=tmp_path)

    definition = loader.load_file(Path("nested/gaming_script.json"))

    assert definition.name == "gaming_script"


def test_absolute_safe_paths_under_base_dir_work(tmp_path: Path) -> None:
    """Absolute paths inside base_dir should be accepted."""

    prompt_path = tmp_path / "gaming_script.json"
    write_prompt_file(prompt_path)
    loader = PromptLoader(base_dir=tmp_path)

    definition = loader.load_file(prompt_path.resolve())

    assert definition.version == 1


def test_missing_files_raise_prompt_load_error(tmp_path: Path) -> None:
    """Missing prompt files should raise PromptLoadError."""

    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load_file(Path("missing.json"))

    assert exc_info.value.code == "prompt_load_file_not_found"


def test_invalid_json_raises_prompt_load_error(tmp_path: Path) -> None:
    """Invalid JSON prompt files should raise PromptLoadError."""

    prompt_path = tmp_path / "invalid.json"
    prompt_path.write_text("{invalid", encoding="utf-8")
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load_file(prompt_path)

    assert exc_info.value.code == "prompt_load_invalid_json"


def test_invalid_definitions_fail_safely(tmp_path: Path) -> None:
    """Invalid prompt definitions should fail without exposing file contents."""

    prompt_path = tmp_path / "invalid_definition.json"
    write_prompt_file(
        prompt_path,
        variables=[{"name": "1invalid", "variable_type": "string", "required": True}],
    )
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        loader.load_file(prompt_path)

    assert exc_info.value.code == "prompt_definition_invalid"
    assert "Create a script" not in str(exc_info.value)


def test_non_json_files_are_rejected(tmp_path: Path) -> None:
    """Only JSON prompt definition files should be accepted."""

    prompt_path = tmp_path / "prompt.yaml"
    prompt_path.write_text("name: invalid", encoding="utf-8")
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load_file(prompt_path)

    assert exc_info.value.code == "prompt_load_invalid_file_type"


def test_directory_traversal_is_rejected(tmp_path: Path) -> None:
    """Relative traversal outside base_dir should be rejected."""

    outside_file = tmp_path.parent / "outside.json"
    write_prompt_file(outside_file)
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load_file(Path("../outside.json"))

    assert exc_info.value.code == "prompt_load_outside_base_dir"


def test_files_outside_base_dir_are_rejected(tmp_path: Path) -> None:
    """Absolute paths outside base_dir should be rejected."""

    outside_file = tmp_path.parent / "outside.json"
    write_prompt_file(outside_file)
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError):
        loader.load_file(outside_file.resolve())


def test_empty_directory_returns_empty_tuple(tmp_path: Path) -> None:
    """Loading an empty directory should return an empty tuple."""

    loader = PromptLoader(base_dir=tmp_path)

    assert loader.load_directory() == ()


def test_recursive_directory_loading_works(tmp_path: Path) -> None:
    """Recursive directory loading should include nested JSON files."""

    write_prompt_file(tmp_path / "a.json", name="alpha_prompt")
    write_prompt_file(tmp_path / "nested" / "b.json", name="beta_prompt")
    loader = PromptLoader(base_dir=tmp_path)

    prompts = loader.load_directory(recursive=True)

    assert [prompt.name for prompt in prompts] == ["alpha_prompt", "beta_prompt"]


def test_non_recursive_loading_excludes_nested_files(tmp_path: Path) -> None:
    """Non-recursive directory loading should ignore nested JSON files."""

    write_prompt_file(tmp_path / "a.json", name="alpha_prompt")
    write_prompt_file(tmp_path / "nested" / "b.json", name="beta_prompt")
    loader = PromptLoader(base_dir=tmp_path)

    prompts = loader.load_directory(recursive=False)

    assert [prompt.name for prompt in prompts] == ["alpha_prompt"]


def test_files_load_in_predictable_order(tmp_path: Path) -> None:
    """Directory loading should sort prompt files predictably."""

    write_prompt_file(tmp_path / "zeta.json", name="zeta_prompt")
    write_prompt_file(tmp_path / "alpha.json", name="alpha_prompt")
    loader = PromptLoader(base_dir=tmp_path)

    prompts = loader.load_directory()

    assert [prompt.name for prompt in prompts] == ["alpha_prompt", "zeta_prompt"]


def test_one_invalid_file_fails_the_directory_load(tmp_path: Path) -> None:
    """A single invalid prompt file should fail the full directory load."""

    write_prompt_file(tmp_path / "valid.json")
    (tmp_path / "invalid.json").write_text("{invalid", encoding="utf-8")
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load_directory()

    assert exc_info.value.code == "prompt_load_directory_failed"
    assert exc_info.value.details == {"path": "invalid.json"}


def test_load_into_registry_registers_prompts(tmp_path: Path) -> None:
    """Loaded prompts should be registered into the supplied registry."""

    write_prompt_file(tmp_path / "a.json", name="alpha_prompt")
    loader = PromptLoader(base_dir=tmp_path)
    registry = create_prompt_registry()

    prompts = loader.load_into_registry(registry)

    assert len(prompts) == 1
    assert registry.contains("alpha_prompt", 1) is True


def test_replace_behavior_is_honored(tmp_path: Path) -> None:
    """Registry replacement should be honored during loader registration."""

    write_prompt_file(tmp_path / "a.json", name="alpha_prompt")
    loader = PromptLoader(base_dir=tmp_path)
    registry = create_prompt_registry()
    loader.load_into_registry(registry)

    with pytest.raises(PromptAlreadyRegisteredError):
        loader.load_into_registry(registry, replace=False)

    prompts = loader.load_into_registry(registry, replace=True)

    assert prompts[0].name == "alpha_prompt"


def test_loader_does_not_modify_prompt_files(tmp_path: Path) -> None:
    """Loading prompt files should not mutate file contents."""

    prompt_path = tmp_path / "a.json"
    write_prompt_file(prompt_path)
    original_contents = prompt_path.read_text(encoding="utf-8")
    loader = PromptLoader(base_dir=tmp_path)

    loader.load_file(prompt_path)

    assert prompt_path.read_text(encoding="utf-8") == original_contents


def test_loader_errors_do_not_expose_file_contents(tmp_path: Path) -> None:
    """Loader errors should avoid exposing prompt file contents."""

    prompt_path = tmp_path / "invalid.json"
    prompt_path.write_text('{"messages": [{"content": "SECRET PROMPT BODY"}]}', encoding="utf-8")
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        loader.load_file(prompt_path)

    assert "SECRET PROMPT BODY" not in str(exc_info.value)


def test_root_load_directory_ignores_manifest_json(tmp_path: Path) -> None:
    """Root directory loading should ignore the prompt manifest file."""

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [],
                "metadata": {"description": "CreatorOS version-controlled prompt asset manifest."},
            }
        ),
        encoding="utf-8",
    )
    write_prompt_file(tmp_path / "research" / "gaming" / "gaming_script.v1.json", name="gaming_script")
    loader = PromptLoader(base_dir=tmp_path)

    prompts = loader.load_directory()

    assert [prompt.name for prompt in prompts] == ["gaming_script"]


def test_existing_category_prompt_files_still_load(tmp_path: Path) -> None:
    """Category directories should continue to load prompt definitions normally."""

    write_prompt_file(tmp_path / "script" / "youtube_shorts_script.v2.json", name="youtube_shorts_script", version=2)
    loader = PromptLoader(base_dir=tmp_path)

    prompts = loader.load_directory(path=Path("script"))

    assert len(prompts) == 1
    assert prompts[0].qualified_name == "youtube_shorts_script:v2"
