"""Provider-independent prompt contracts, registry, rendering, and loading for CreatorOS."""

from creatoros.prompts.assets import (
    PromptAssetCategory,
    PromptAssetManifest,
    PromptAssetManifestEntry,
)
from creatoros.prompts.bootstrap import create_builtin_prompt_registry, load_builtin_prompts
from creatoros.prompts.discovery import PromptAssetDiscovery, PromptAssetRecord
from creatoros.prompts.enums import PromptFormat, PromptRole, PromptStatus, PromptVariableType
from creatoros.prompts.loader import PromptLoader
from creatoros.prompts.manifest import PromptManifestLoader
from creatoros.prompts.models import (
    PromptDefinition,
    PromptMessage,
    PromptVariable,
    RenderedPrompt,
)
from creatoros.prompts.naming import (
    PromptAssetName,
    build_prompt_asset_filename,
    parse_prompt_asset_filename,
)
from creatoros.prompts.registry import PromptRegistry, create_prompt_registry, get_prompt_registry
from creatoros.prompts.renderer import PromptRenderer
from creatoros.prompts.research import (
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EXPAND_KEYWORDS,
    render_gaming_discover_trends,
    render_gaming_evaluate_opportunity,
    render_gaming_expand_keywords,
)

__all__ = [
    "GAMING_DISCOVER_TRENDS",
    "GAMING_EVALUATE_OPPORTUNITY",
    "GAMING_EXPAND_KEYWORDS",
    "PromptAssetCategory",
    "PromptAssetDiscovery",
    "PromptAssetManifest",
    "PromptAssetManifestEntry",
    "PromptAssetName",
    "PromptAssetRecord",
    "PromptDefinition",
    "PromptFormat",
    "PromptLoader",
    "PromptManifestLoader",
    "PromptMessage",
    "PromptRegistry",
    "PromptRenderer",
    "PromptRole",
    "PromptStatus",
    "PromptVariable",
    "PromptVariableType",
    "RenderedPrompt",
    "build_prompt_asset_filename",
    "create_builtin_prompt_registry",
    "create_prompt_registry",
    "get_prompt_registry",
    "load_builtin_prompts",
    "parse_prompt_asset_filename",
    "render_gaming_discover_trends",
    "render_gaming_evaluate_opportunity",
    "render_gaming_expand_keywords",
]
