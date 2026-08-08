# CreatorOS

CreatorOS is a modular AI-powered gaming content factory.

## Current Phase

Phase 1 - Foundation

## Initial Goal

Build a reliable pipeline for trend research, script generation, and storyboarding.

## Environment Setup

1. Create the virtual environment.
2. Activate `.venv`.
3. Install project dependencies.
4. Run tests before committing changes.

## CLI

Use the CreatorOS CLI foundation to inspect configuration, mock providers, and workflow state behavior:

```bash
python -m creatoros --help
python -m creatoros config validate
python -m creatoros config show
python -m creatoros providers list --mock
python -m creatoros providers health --mock
python -m creatoros workflows transitions running
python -m creatoros workflows demo-state
```

Mock providers are local and free.
`workflows demo-state` demonstrates workflow state management only.
The first end-to-end content workflow remains deferred to Step 10.

## First Executable Demo Workflow

Run the first local deterministic gaming workflow through the CLI:

```bash
python -m creatoros run gaming
python -m creatoros run gaming --approve
python -m creatoros run gaming --game Roblox --topic "funny myths" --approve
```

This workflow uses local deterministic mock providers only.
It performs no real trend research, creates no real media, and publishes only to a mock publishing provider.
Without `--approve`, it stops at the publishing approval gate.
Real provider integrations belong to later milestones.

## Prompt Foundation

CreatorOS now includes a provider-independent prompt-system foundation under `creatoros/prompts`.

- Prompt definitions are validated through typed Pydantic contracts.
- Prompt rendering uses explicit variables rather than ad hoc string assembly.
- Prompt definitions can be registered and resolved through a platform-owned registry.
- Prompt assets can be loaded from the configured prompts directory as validated JSON files.
- Prompt assets are organized under the repository `prompts/` directory by category.
- Prompt asset filenames use the format `<name>.v<version>.json`.
- `prompts/manifest.json` is a descriptive, validated manifest for discovery and verification rather than a runtime database.
- Prompt discovery calculates SHA-256 checksums from exact file bytes.

This foundation does not claim that production prompt catalogs, real LLM workflows, or remote prompt management are already complete. It establishes the architectural base for those later milestones.

## Structured Parsing Foundation

CreatorOS now includes a provider-independent structured-output parsing foundation under `creatoros/parsing`.

- Structured parsing sits between untrusted provider text and CreatorOS domain or application models.
- Provider text must not flow directly into domain objects without normalization and validation.
- The parsing layer is provider-independent and does not integrate any real LLM vendor in this milestone.
- The current v1 parser supports deterministic label/value structured text only.
- Research prompt outputs now have typed parsers for trend discovery, opportunity evaluation, and keyword expansion.
- Script prompt outputs now have typed parsers for YouTube Shorts scripts, gaming hooks, and gaming CTAs.
- Storyboard prompt outputs now have typed parsers for scene breakdowns, visual direction, and timing review.
- Media prompt outputs now have typed parsers for thumbnail concepts, scene visuals, scene motion, and narration direction.
- Review prompt outputs now have typed advisory parsers for script, evidence, storyboard, and publication-readiness reviews.
- A `ParserRegistry` now maps stable logical prompt names to typed parser registrations.
- Each parser registration declares its expected output model type explicitly.
- Prompt registration and parser registration remain separate concerns.
- Builtin prompt/parser contract validation detects drift between prompt assets and typed parser registrations.
- All 17 current builtin prompt assets now have typed parser registrations.
- Keyword-list parsing supports simple `- item` bullet syntax only.
- Repeating storyboard scenes use a dedicated safe scene-block parser rather than a brittle flat-field approximation.
- JSON parsing is not part of this milestone.
- Markdown-table parsing is not part of this milestone.
- Raw LLM responses must not be logged by default by the parsing layer.
- No repair or retry mechanism exists yet.

Agents and workflows are not yet migrated to consume these typed parsers automatically. Review outputs remain advisory only, and `ready_for_human_review` is not publication approval.
Provider integration can now resolve typed parsers through a provider-independent registry contract instead of hardcoded prompt-family branching, but no real LLM provider is integrated yet and no workflow behavior changed in this milestone.

## Prompt Asset Structure

The current prompt repository structure is:

```text
prompts/
    manifest.json
    research/
        gaming/
        common/
    script/
    storyboard/
    narration/
    thumbnail/
    metadata/
    review/
    publishing/
```

Prompt names are global logical identifiers and should be unique enough to avoid collisions without relying on folder prefixes. The manifest supports validation and inventory, but CreatorOS does not automatically register prompt assets from the manifest at runtime yet.

## Built-In Research Prompts

CreatorOS now includes a first set of built-in provider-independent prompt assets for gaming workflows:

- `gaming_cta`
- `gaming_discover_trends`
- `gaming_evaluate_opportunity`
- `gaming_expand_keywords`
- `gaming_hook`
- `storyboard_scene_breakdown`
- `storyboard_timing_review`
- `storyboard_visual_direction`
- `youtube_shorts_script`

These prompts are stored as validated JSON assets under `prompts/research/gaming/`, `prompts/script/`, and `prompts/storyboard/`, represented in `prompts/manifest.json`, and loadable through the platform prompt registry without provider calls. Stable logical prompt names should be used from application code instead of filesystem paths.

CreatorOS also now includes provider-independent media-support prompt assets for:

- `gaming_thumbnail_concept`
- `gaming_scene_visual_prompt`
- `gaming_scene_motion_prompt`
- `gaming_narration_direction`

These media-support prompts remain local prompt assets only. They do not invoke image generation, video generation, or narration providers, and they do not imply that downstream media engines have already been implemented.

CreatorOS also includes provider-independent review prompt assets for:

- `gaming_script_quality_review`
- `gaming_evidence_consistency_review`
- `gaming_storyboard_quality_review`
- `gaming_publication_readiness_review`

These review prompts are advisory quality gates only. They use supplied inputs only, do not browse, do not independently fact-check, do not publish, and do not bypass the human approval model.

Use the CLI to inspect the manifest, discover assets, list registered prompts, and render the deterministic research prompt locally:

```bash
python -m creatoros prompts manifest show
python -m creatoros prompts manifest validate
python -m creatoros prompts discover
python -m creatoros prompts list
python -m creatoros parsers list
python -m creatoros parsers validate
python -m creatoros prompts render gaming_discover_trends
python -m creatoros prompts render gaming_discover_trends --game Roblox --topic "funny myths" --signals "Players are discussing recurring myths about game mechanics." --show-content
python -m creatoros prompts render youtube_shorts_script
python -m creatoros prompts render youtube_shorts_script --title "Roblox: Funny Myths" --game Roblox --topic "funny myths" --angle "test three popular myths" --hook-direction "challenge a common belief" --source-summary "Supplied research notes discuss recurring myths about game mechanics." --show-content
python -m creatoros prompts render gaming_hook --show-content
python -m creatoros prompts render gaming_cta --show-content
python -m creatoros prompts render storyboard_scene_breakdown
python -m creatoros prompts render storyboard_scene_breakdown --title "Roblox: Funny Myths" --game Roblox --hook "You probably still believe this Roblox myth." --body "Players often repeat three myths about game mechanics." --ending "Now you know which claims deserve checking." --call-to-action "Which myth should we test next?" --duration 30 --show-content
python -m creatoros prompts render storyboard_visual_direction --show-content
python -m creatoros prompts render storyboard_timing_review --show-content
python -m creatoros prompts render gaming_thumbnail_concept --show-content
python -m creatoros prompts render gaming_scene_visual_prompt --show-content
python -m creatoros prompts render gaming_scene_motion_prompt --show-content
python -m creatoros prompts render gaming_narration_direction --show-content
```

By default, `prompts render` shows prompt metadata only. Full rendered prompt content is shown only when `--show-content` is provided. These commands render locally, do not call an LLM provider, and do not imply that real AI generation is already wired into the demo workflow.

The current research, script, storyboard, thumbnail, narration, and review prompt output contracts are text-based. All current prompt families now have typed provider-independent parsing support, but parser output still does not change workflow state automatically. Review prompts remain advisory and publication readiness means ready for human review, not approved for publication. Workflow integration for parsed outputs, real image generation, real video generation, real narration generation, and downstream media-production integration will be added in later milestones.
