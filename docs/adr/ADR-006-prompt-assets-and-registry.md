# ADR-006: Prompt Assets and Registry

- Status: Accepted
- Date: 2026-08-05

## Context

CreatorOS depends on prompts to support research, generation, evaluation, and other intelligence-layer responsibilities. If prompts are embedded directly inside provider adapters or scattered through implementation code, they become difficult to review, validate, version, test, and replace.

The platform also requires provider independence. Prompt assets should describe CreatorOS tasks and contracts rather than the request format of any single LLM vendor. Without a platform-owned prompt subsystem, prompt behavior can drift into provider-specific logic, making future migrations, testing, and governance more difficult.

At the current stage of the roadmap, CreatorOS needs a prompt foundation that is simple, explicit, and compatible with the modular monolith architecture. That foundation must support typed validation, deterministic rendering, safe loading from disk, and stable lookup by name and version.

## Decision

CreatorOS will treat prompts as versioned, provider-independent application assets managed through a platform-owned prompt subsystem.

That subsystem will include:

- Typed prompt definition models
- Typed prompt variable definitions and validation
- A deterministic prompt renderer
- A prompt registry with explicit name and version resolution
- A prompt loader for validated prompt assets stored on disk
- A manifest for describing versioned prompt assets
- Discovery rules for prompt asset categories, filenames, and checksums

The initial asset format will be validated JSON files loaded from the configured prompts directory. Prompt assets will remain outside the Python package in a version-controlled repository directory structure organized by category. A validated manifest may describe those assets for verification and inventory purposes, but it is not a persistence layer or runtime database. Prompt rendering will occur before provider invocation, and provider adapters may transform rendered prompt output into vendor-specific request structures only at the integration boundary.

## Rationale

This decision preserves architecture boundaries by keeping task definitions inside CreatorOS instead of inside external provider implementations. It also improves replaceability because prompt contracts can remain stable even when the selected LLM provider changes.

Typed prompt contracts improve testability and safety. Required variables, supported value types, message structure, and version metadata can all be validated before a provider call is attempted. This reduces runtime ambiguity and makes failures easier to diagnose.

A registry-based design also supports long-term maintainability. Prompt lookup by name and version creates a stable pattern for controlled evolution, while keeping the implementation simple enough for current needs. Starting with validated JSON assets avoids premature complexity such as database-backed prompt management or dynamic remote prompt editing before those capabilities are operationally justified.

The first concrete implementation of this decision is a small set of built-in gaming research prompt assets that can be validated from the manifest, loaded into a fresh registry, and rendered locally through explicit helper functions and CLI commands. This keeps the initial scope aligned with the current roadmap while proving the subsystem against real assets instead of placeholder structure alone.

## Consequences

Future prompt work in CreatorOS should use the prompt subsystem rather than introducing ad hoc string templates in unrelated modules. Prompt changes become reviewable product changes and should be tested and documented where behavior is important.

Provider adapters must not become the source of truth for prompt definitions. They may adapt rendered prompts to external APIs, but they should not own prompt lifecycle, validation, or versioning.

This decision also creates a responsibility to maintain prompt contracts carefully. Prompt naming, variable definitions, and versioning should remain consistent so that prompts can evolve without hidden behavioral changes.

## Future Considerations

Future versions of CreatorOS may introduce additional prompt asset formats, richer metadata, prompt catalogs by workflow or engine, fixture libraries, or persistence-backed prompt management. Those changes should preserve the principle that prompts are platform-owned assets resolved through explicit contracts rather than vendor-owned strings hidden behind provider code.

If future operational needs justify remote prompt storage, approval workflows, or experiment-driven prompt selection, those capabilities should be introduced through additional ADRs rather than by bypassing the prompt subsystem established here.
