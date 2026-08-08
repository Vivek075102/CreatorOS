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

Use the CLI to inspect the manifest, discover assets, list registered prompts, and render the deterministic research prompt locally:

```bash
python -m creatoros prompts manifest show
python -m creatoros prompts manifest validate
python -m creatoros prompts discover
python -m creatoros prompts list
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
```

By default, `prompts render` shows prompt metadata only. Full rendered prompt content is shown only when `--show-content` is provided. These commands render locally, do not call an LLM provider, and do not imply that real AI generation is already wired into the demo workflow.

The current research, script, and storyboard prompt output contracts are text-based. Storyboard prompts currently define scene breakdown, provider-independent visual direction, and timing-review contracts only. Structured parsing, real storyboard generation, and downstream media generation integration will be added in later milestones.
