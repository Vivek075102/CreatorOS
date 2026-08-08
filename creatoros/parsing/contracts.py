"""Prompt and parser contract validation helpers."""

from __future__ import annotations

from pydantic import Field

from creatoros.domain import CreatorOSModel
from creatoros.parsing.registry import ParserRegistry
from creatoros.prompts.registry import PromptRegistry


class PromptParserContractReport(CreatorOSModel):
    """Deterministic report describing builtin prompt/parser alignment."""

    valid: bool
    prompt_names: tuple[str, ...]
    parser_names: tuple[str, ...]
    missing_parsers: tuple[str, ...]
    orphan_parsers: tuple[str, ...]
    metadata: dict[str, object] = Field(default_factory=dict)


def validate_builtin_prompt_parser_contracts(
    prompt_registry: PromptRegistry,
    parser_registry: ParserRegistry,
) -> PromptParserContractReport:
    """Compare builtin prompt logical names and parser registrations safely."""

    prompt_names = tuple(definition.name for definition in prompt_registry.list_prompts())
    parser_names = parser_registry.list_prompt_names()
    parser_name_set = set(parser_names)
    prompt_name_set = set(prompt_names)

    missing_parsers = tuple(name for name in prompt_names if name not in parser_name_set)
    orphan_parsers = tuple(name for name in parser_names if name not in prompt_name_set)

    return PromptParserContractReport(
        valid=not missing_parsers and not orphan_parsers,
        prompt_names=prompt_names,
        parser_names=parser_names,
        missing_parsers=missing_parsers,
        orphan_parsers=orphan_parsers,
        metadata={
            "prompt_count": len(prompt_names),
            "parser_count": len(parser_names),
        },
    )


__all__ = [
    "PromptParserContractReport",
    "validate_builtin_prompt_parser_contracts",
]
