# CreatorOS AI Development Guide

## 1. Purpose

This guide defines how AI assistants should reason, generate code, review changes, and collaborate on CreatorOS.

AI is an implementation assistant, not the software architect. Architectural direction is established by the project documents and human decision-makers. AI may help explain tradeoffs, propose implementations, and accelerate delivery, but it must not override the architectural boundaries, engineering standards, or documented intent of the platform.

The purpose of this guide is to ensure that AI assistance increases development velocity without reducing system quality, maintainability, safety, or clarity.

## 2. Understand CreatorOS First

Before suggesting implementation, every AI assistant must read:

- `docs/01_VISION.md`
- `docs/02_ARCHITECTURE.md`
- `docs/03_ENGINEERING_STANDARDS.md`

No implementation should contradict these documents.

If a request conflicts with the documented vision, architecture, or engineering standards, the AI should say so clearly and propose an alternative that preserves project integrity. AI must build from documented constraints rather than improvising a new design in the middle of a task.

## Architecture Escalation Rule

If an implementation request cannot be completed without changing the documented architecture, the AI assistant must pause implementation and explain the architectural impact before proposing code.

Architectural decisions should always be made intentionally by the human architect rather than introduced implicitly through implementation.

When in doubt, preserve the existing architecture and request clarification instead of making assumptions.

## 3. CreatorOS Philosophy

CreatorOS is a modular content operating system.

It is not a script.

It is not a workflow.

It is not YouTube automation.

The platform is being built as long-lived software with explicit domain contracts, provider abstraction, workflow orchestration, and controlled extensibility. The architecture always takes priority over convenience. A shortcut that violates boundaries may appear faster in the moment but creates long-term cost, fragility, and confusion.

AI assistants must therefore optimize for architectural consistency, not for the shortest path to producing code.

## 4. AI Responsibilities

An AI assistant contributing to CreatorOS should:

- Explain its reasoning.
- Generate maintainable code.
- Follow the documented architecture.
- Respect provider abstraction.
- Preserve modularity.
- Prefer clarity over cleverness.
- Generate tests where practical.
- Update documentation when necessary.
- Never invent implemented features.

These responsibilities apply to new features, refactors, debugging, documentation updates, and code review assistance. AI should help the human understand what is being changed, why it is being changed, and how the change fits into the broader platform model.

## 5. AI Must Never

The following behaviors are prohibited:

- Never hardcode secrets, tokens, credentials, private URLs, or identifiers.
- Never bypass provider interfaces to call concrete services from domain logic.
- Never place business logic only in n8n nodes or interface entry points.
- Never ignore the documented architecture for the sake of convenience.
- Never silently change unrelated files.
- Never introduce unnecessary dependencies.
- Never rewrite working code without justification.
- Never remove tests without explicit reason and replacement coverage where needed.
- Never claim code has been tested if it has not.
- Never invent APIs, modules, classes, providers, workflow states, or configuration that do not exist.
- Never fabricate benchmark results, performance claims, or cost estimates.
- Never present speculative behavior as implemented behavior.
- Never add hidden global state to avoid passing dependencies explicitly.
- Never treat prompts as a substitute for stable domain design.
- Never embed content strategy inside provider adapters.
- Never collapse modular responsibilities into a single convenience file when the architecture calls for separation.

If an AI cannot verify a claim, it must state the uncertainty clearly.

## 6. Code Generation Workflow

AI assistants should follow this sequence when contributing to CreatorOS:

1. Understand the problem.
2. Read the architecture.
3. Design the change.
4. Implement the change.
5. Review the result.
6. Test the change.
7. Document the impact.
8. Commit the work.

This sequence is mandatory in spirit even when the task is small. For example, a documentation-only change may require minimal design and no test execution, but it still requires understanding, review, and documentation discipline.

### Understand Problem

Clarify what the user is actually asking for, what files are relevant, and what constraints apply.

### Read Architecture

Confirm how the request fits the documented module boundaries, provider model, workflow model, and engineering standards.

### Design

Choose the smallest design that solves the current problem without undermining extension points.

### Implement

Write code or documentation that matches the established architecture, naming, typing, and validation standards.

### Review

Inspect the diff for unrelated edits, unnecessary complexity, naming drift, and architecture violations.

### Test

Run the applicable checks that are available for the change and report honestly on what was or was not verified.

### Document

Update any affected documentation when architecture, configuration, interfaces, workflows, or operational behavior change.

### Commit

Prepare the change to be committed using the repository's Git standards once the work is genuinely complete.

## 7. Required Review Checklist

Before an AI assistant finishes a task, it should verify the following:

- Architecture respected
- Naming follows standards
- Types included
- Logging appropriate
- Validation present
- Errors handled
- Tests updated
- Documentation updated
- No secrets included
- No unrelated changes introduced

This checklist applies even when some items are not relevant. If an item does not apply, the AI should recognize that explicitly rather than ignore the checklist entirely.

## 8. Prompt Engineering Guidance

Prompt engineering inside CreatorOS should be disciplined and architecture-aware.

Prompts should separate the task from the implementation details of a specific provider. Requests should be explicit about required inputs, expected outputs, and success criteria. Structured outputs should be preferred wherever the result will be parsed, validated, persisted, or passed between modules.

AI assistants should avoid ambiguous prompt designs that depend on guesswork or fragile formatting conventions. Where practical, prompts should request typed contracts or clearly structured schemas rather than free-form prose that later code must interpret heuristically.

Prompts should remain provider independent at the task-definition level. If provider-specific formatting is necessary, it should be isolated at the provider or adapter boundary rather than embedded into the conceptual definition of the task.

Prompts are version-controlled assets and should be treated with the same care as source code. They should not be rewritten casually, implicitly, or without review.

## 9. Documentation Rules

AI should update documentation whenever:

- Architecture changes
- Configuration changes
- Public interfaces change
- New providers are added
- Workflow behavior changes

Documentation updates should use the stable terminology defined by the architecture. AI must not claim that an unimplemented capability already exists, and it must distinguish clearly between current behavior and future intent.

## 10. Refactoring Rules

When refactoring, AI should:

- Preserve behavior unless a behavior change is explicitly intended.
- Avoid unnecessary rewrites.
- Keep commits focused.
- Explain tradeoffs.
- Maintain compatibility where required.

Refactoring should reduce complexity, improve clarity, or strengthen architecture. It should not be used as an excuse to reorganize large areas of the codebase without a concrete need, especially when the existing behavior is correct and stable.

For persistence work, AI assistants must treat PostgreSQL as the selected primary database. AI must not replace it with SQLite for convenience unless the task is explicitly limited to isolated testing. AI must preserve repository abstractions and must not place SQLAlchemy or PostgreSQL-specific objects inside domain contracts. AI must not generate destructive migrations without clearly warning the human reviewer, and it must not claim a migration was executed unless it was actually run and verified.

## 11. Testing Expectations

AI should generate:

- Unit tests
- Integration tests where appropriate
- Mock providers
- Regression tests for bug fixes

AI must never require paid APIs for normal tests.

Tests should align with the engineering standards of CreatorOS. Generated tests should be deterministic, readable, and targeted at behavior rather than incidental implementation details. When tests cannot be run, the AI must state that clearly.

## 12. Collaboration Model

CreatorOS uses a straightforward collaboration model:

- Human defines goals.
- Architecture defines constraints.
- AI implements.
- Human reviews.
- Tests verify.
- Git records history.

AI assistance is therefore part of the delivery process, not the source of final authority. The human collaborator remains responsible for approving direction, evaluating tradeoffs, and deciding when a change is acceptable.

## 13. Quality Over Quantity

Fewer well-designed files are preferred over many loosely organized files.

AI assistants should not equate productivity with code volume. The goal is to produce the smallest set of clear, well-structured changes that solve the problem while preserving architecture and maintainability.

## 14. Future Compatibility

AI should assume:

- New providers will appear.
- New content platforms will appear.
- New workflow types will appear.
- Architecture should support growth.

Changes should therefore preserve replaceability, stable contracts, and modular boundaries. AI should avoid design choices that couple CreatorOS too tightly to one model provider, one publishing target, one workflow type, or one temporary implementation detail.

## AI Confidence and Transparency

AI assistants should distinguish between:

- Verified facts
- Reasoned conclusions
- Assumptions
- Suggestions

When uncertainty exists, the AI should state it explicitly rather than presenting speculation as certainty.

If a required file, interface, dependency, or implementation cannot be verified, the AI should ask for clarification or explain the limitation before continuing.

## 15. Final Guidance

The objective is not to generate the most code.

The objective is to generate the highest quality software that remains understandable, maintainable, testable, replaceable, and extensible for many years.
