"""Bootstrap helpers for loading builtin CreatorOS prompt assets."""

from __future__ import annotations

from pathlib import Path

from creatoros.prompts.discovery import PromptAssetDiscovery
from creatoros.prompts.loader import PromptLoader
from creatoros.prompts.manifest import PromptManifestLoader
from creatoros.prompts.models import PromptDefinition
from creatoros.prompts.registry import PromptRegistry, create_prompt_registry

BUILTIN_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _resolve_builtin_base_dir(base_dir: Path | None) -> Path:
    """Resolve the builtin prompt asset directory without reading runtime settings."""

    return (BUILTIN_PROMPTS_DIR if base_dir is None else Path(base_dir)).resolve()


def load_builtin_prompts(
    registry: PromptRegistry,
    *,
    base_dir: Path | None = None,
    replace: bool = False,
) -> tuple[PromptDefinition, ...]:
    """Load validated builtin prompt assets into the supplied registry."""

    resolved_base_dir = _resolve_builtin_base_dir(base_dir)
    manifest_loader = PromptManifestLoader(base_dir=resolved_base_dir)
    discovery = PromptAssetDiscovery(base_dir=resolved_base_dir)
    loader = PromptLoader(base_dir=resolved_base_dir)

    manifest = manifest_loader.load()
    discovery.validate_manifest(manifest)

    loaded_definitions: list[PromptDefinition] = []
    for entry in manifest.list_entries():
        definition = loader.load_file(Path(entry.path))
        registry.register(definition, replace=replace)
        loaded_definitions.append(definition.model_copy(deep=True))

    return tuple(definition.model_copy(deep=True) for definition in loaded_definitions)


def create_builtin_prompt_registry(
    *,
    base_dir: Path | None = None,
) -> PromptRegistry:
    """Create a fresh registry populated with validated builtin prompt assets."""

    registry = create_prompt_registry()
    load_builtin_prompts(registry, base_dir=base_dir)
    return registry


__all__ = [
    "create_builtin_prompt_registry",
    "load_builtin_prompts",
]
