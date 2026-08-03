# ADR-001: PostgreSQL as Primary Database

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS requires a relational persistence layer that can support workflow state, structured domain records, publication history, analytics, experiments, provider usage tracking, and future operational growth. The platform is intended to run consistently across development and production environments, and its architectural direction already emphasizes stable contracts, maintainability, and reduced migration risk.

An early alternative was to begin with SQLite and defer a move to PostgreSQL until later. That option can be attractive in small prototypes, but it introduces differences between local development and production behavior, narrows the available relational and concurrency model, and increases the risk of a disruptive migration once more workflow state and operational history accumulate.

## Decision

CreatorOS will use PostgreSQL as its primary relational database for both development and production environments.

SQLite remains acceptable only for isolated unit tests, temporary experiments, and narrowly scoped test fixtures. It is not the normal application database.

## Rationale

PostgreSQL was selected because it aligns better with the long-term platform goals of CreatorOS.

It provides consistency between local development and production, which reduces environment-specific surprises and lowers operational drift. It supports strong relational modeling, robust transaction handling, and concurrency characteristics better suited to workflow-oriented platform behavior.

PostgreSQL also supports JSON and semi-structured data where that is genuinely useful, while still encouraging disciplined relational design. Its indexing and query capabilities provide a practical foundation for workflow inspection, analytics, audit history, and future reporting requirements.

Most importantly, selecting PostgreSQL early reduces migration risk. CreatorOS is designed as a long-lived platform, not as a throwaway prototype. Starting with the intended production-grade relational foundation avoids avoidable architectural churn later.

## Consequences

This decision means local development environments will need access to a PostgreSQL database or an approved equivalent development environment. Persistence implementation should therefore be designed intentionally rather than postponed.

The decision also increases the importance of disciplined database boundaries. Domain and application code must remain behind repository or persistence interfaces and must not become tightly coupled to PostgreSQL-specific details. PostgreSQL-specific capabilities may be used where they provide real value, but they should remain isolated within persistence implementations.

This decision does not mean that CreatorOS is adopting complex distributed database architecture, clustering, sharding, or premature high-availability infrastructure. It only establishes PostgreSQL as the primary relational foundation.

## Future Considerations

Future implementation work should establish the persistence stack using SQLAlchemy 2.x and Alembic while preserving domain independence from ORM models and SQL-specific behavior.

PostgreSQL-specific features such as JSONB, advanced indexing, or specialized query patterns should be adopted only when justified by real workflow needs and should not leak unnecessarily into domain contracts.

If future operational requirements ever justify a different persistence strategy, that change should be documented in a new ADR rather than introduced implicitly through implementation.
