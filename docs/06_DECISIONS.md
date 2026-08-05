# CreatorOS Architecture Decision Records

## Purpose of ADRs

Architecture Decision Records, or ADRs, capture important technical and architectural decisions made for CreatorOS. Their purpose is to preserve the reasoning behind decisions that shape the platform so future contributors can understand not only what was chosen, but why it was chosen and what tradeoffs were considered.

ADRs exist to reduce repeated debate, avoid accidental reversal of intentional design choices, and provide stable historical context as CreatorOS evolves.

## When to Create a New ADR

A new ADR should be created when a decision meaningfully affects the architecture, operational model, platform boundaries, or long-term maintainability of CreatorOS.

Examples include:

- selection of core infrastructure
- changes to persistence strategy
- workflow orchestration choices
- provider abstraction decisions
- deployment model changes
- automation and approval model changes
- significant boundary or dependency rule changes

Routine implementation details, minor refactors, and short-lived local experiments do not require ADRs unless they introduce an architectural commitment.

## ADR Numbering Rules

CreatorOS ADRs use sequential numbering in the format `ADR-001`, `ADR-002`, and so on.

Numbering rules are:

- Numbers are assigned in increasing sequence.
- Each ADR number is unique and must not be reused.
- File names should use the pattern `ADR-XXX-short-title.md`.
- Numbers remain stable even if an ADR is later superseded or deprecated.
- New ADRs should be added to this index when they are created.

## ADR Lifecycle

Each ADR should include a status. CreatorOS uses the following lifecycle states:

- `Proposed`: the decision is under review and is not yet treated as project direction.
- `Accepted`: the decision has been approved and should guide implementation.
- `Superseded`: the decision was previously accepted but has been replaced by a newer ADR.
- `Deprecated`: the decision remains part of project history but should no longer be used for new work.

Status changes should be intentional and documented inside the affected ADR.

## ADR Template

New ADRs should follow this structure:

```text
# ADR-XXX: Title

- Status: Proposed | Accepted | Superseded | Deprecated
- Date: YYYY-MM-DD

## Context

Describe the problem, constraints, and forces that created the need for a decision.

## Decision

State the decision clearly and directly.

## Rationale

Explain why this option was chosen over alternatives.

## Consequences

Describe the expected benefits, costs, limitations, and obligations introduced by the decision.

## Future Considerations

Describe how the decision may evolve, what would trigger reconsideration, and what future work it implies.
```

## Current ADRs

| Number | Title | Status | Summary |
| --- | --- | --- | --- |
| ADR-000 | Project Principles | Accepted | Defines the permanent architectural principles that guide every future CreatorOS decision. |
| ADR-001 | PostgreSQL as Primary Database | Accepted | Selects PostgreSQL as the primary relational database for development and production while limiting SQLite to isolated testing and experiments. |
| ADR-002 | Modular Monolith | Accepted | Establishes CreatorOS as a modular monolith rather than a microservices system in its initial architecture. |
| ADR-003 | Provider Pattern | Accepted | Requires provider abstractions instead of direct vendor coupling to preserve replaceability, testing flexibility, and long-term maintainability. |
| ADR-004 | Human Approval and Level 4 Automation | Accepted | Selects Level 4 automation as the target operating model to preserve human oversight and controlled publishing. |
| ADR-005 | Python Platform Stack | Accepted | Selects Python, PostgreSQL, SQLAlchemy, Alembic, and Pydantic as the foundational implementation stack for CreatorOS. |
| ADR-006 | Prompt Assets and Registry | Accepted | Treats prompts as versioned, provider-independent application assets loaded through validated contracts and resolved through a registry. |
