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

This foundation does not claim that production prompt catalogs, real LLM workflows, or remote prompt management are already complete. It establishes the architectural base for those later milestones.
