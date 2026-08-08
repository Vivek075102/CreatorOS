"""Unit tests for prompt/parser contract validation."""

from __future__ import annotations

from pathlib import Path

from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    ParserRegistration,
    build_builtin_parser_registry,
    create_parser_registry,
    validate_builtin_prompt_parser_contracts,
)
from creatoros.prompts import create_builtin_prompt_registry


class StubOutput(CreatorOSModel):
    """Minimal output model used for contract validation tests."""

    value: str


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_current_builtin_contract_report_is_valid() -> None:
    """The current builtin prompt/parser contract should be fully aligned."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.valid is True


def test_builtin_contract_report_represents_exactly_seventeen_prompt_names() -> None:
    """All builtin prompt logical names should be represented in the report."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert len(report.prompt_names) == 17


def test_builtin_contract_report_represents_exactly_seventeen_parser_names() -> None:
    """All builtin parser registrations should be represented in the report."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert len(report.parser_names) == 17


def test_builtin_contract_report_has_no_missing_parsers() -> None:
    """A valid builtin contract report should not miss parser registrations."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.missing_parsers == ()


def test_builtin_contract_report_has_no_orphan_parsers() -> None:
    """A valid builtin contract report should not contain orphan parser registrations."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.orphan_parsers == ()


def test_missing_parser_is_detected() -> None:
    """Validation should identify builtin prompts that lack parser registrations."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = create_parser_registry()

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.valid is False
    assert len(report.missing_parsers) == 17


def test_orphan_parser_is_detected() -> None:
    """Validation should identify parser registrations without builtin prompts."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="orphan_prompt",
            parser=lambda text: StubOutput(value=text),
            output_model_type=StubOutput,
        )
    )

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.valid is False
    assert report.orphan_parsers == ("orphan_prompt",)


def test_report_ordering_is_deterministic() -> None:
    """Contract report ordering should remain stable across repeated validation."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()

    first = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)
    second = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert first == second


def test_validation_does_not_execute_parsers() -> None:
    """Contract validation should compare names only without running parsers."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="gaming_discover_trends",
            parser=lambda text: (_ for _ in ()).throw(AssertionError("parser executed")),
            output_model_type=StubOutput,
        )
    )

    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert report.valid is False


def test_validation_does_not_mutate_prompt_registry() -> None:
    """Contract validation should not alter prompt registry state."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()
    before = tuple(definition.qualified_name for definition in prompt_registry.list_prompts())

    validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    after = tuple(definition.qualified_name for definition in prompt_registry.list_prompts())
    assert after == before


def test_validation_does_not_mutate_parser_registry() -> None:
    """Contract validation should not alter parser registry state."""

    prompt_registry = create_builtin_prompt_registry(base_dir=_repo_prompts_dir())
    parser_registry = build_builtin_parser_registry()
    before = parser_registry.list_prompt_names()

    validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    assert parser_registry.list_prompt_names() == before
