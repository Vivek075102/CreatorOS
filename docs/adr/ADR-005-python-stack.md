# ADR-005: Python Platform Stack

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS requires a practical implementation stack that supports orchestration, provider integration, workflow processing, validation, persistence, testing, and long-term maintainability. The stack must support rapid iteration while remaining suitable for production-quality engineering and clear architectural boundaries.

The selected platform direction also needs to align with the documented architecture: modular application structure, provider abstractions, validation boundaries, repository-style persistence, and workflow-oriented execution.

## Decision

CreatorOS selects the following foundational implementation stack:

- Python as the primary application language
- PostgreSQL as the primary relational database
- SQLAlchemy 2.x as the ORM and database toolkit
- Alembic for schema migrations
- Pydantic for validation and structured data boundaries

## Rationale

Python is well suited to the orchestration-heavy, integration-heavy, and AI-adjacent nature of CreatorOS. It supports rapid iteration, a strong ecosystem for provider integration, readable application code, and practical testing workflows.

PostgreSQL provides the relational foundation appropriate for workflow state, domain records, publication history, analytics, and operational growth. It supports the consistency and data modeling strength required by the platform.

SQLAlchemy 2.x provides a mature persistence toolkit that can support explicit data access patterns, repository-style boundaries, and controlled use of relational features. It is flexible enough to support a modular monolith without forcing domain models to collapse into database implementation details.

Alembic provides an explicit migration path for schema evolution, which is important for a platform expected to preserve workflow history and structured persisted state over time.

Pydantic supports clear validation boundaries for configuration, external inputs, provider outputs, and structured workflow data. It aligns well with CreatorOS principles around explicit contracts and rejection of invalid states early.

## Consequences

This decision establishes a coherent implementation direction, but it also creates responsibilities. Domain models must remain separate from ORM models. Validation boundaries must be explicit. Persistence logic must be isolated. Migration discipline must be maintained from the beginning.

The selected stack does not imply that every part of the persistence and workflow implementation already exists. It only establishes the intended foundation for implementation work.

The stack also narrows future choices in a helpful way. Contributors should build on these tools unless there is a strong architectural reason to change direction.

## Future Considerations

Future refinements may include additional tooling around testing, asynchronous workloads, provider routing, or operational observability. Those additions should complement the selected stack rather than bypass its architectural boundaries.

If major components of the stack ever need to change, that change should be made deliberately and documented through a future ADR with clear migration reasoning and compatibility implications.
