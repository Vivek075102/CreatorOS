# ADR-002: Modular Monolith

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS is being built as a long-term content operating system with multiple architectural layers, stable domain contracts, provider abstractions, orchestration rules, and human approval gates. At the same time, the current scope is intentionally narrow: one private creator, one initial niche, and a limited set of high-value workflows.

This creates an important decision point. CreatorOS could begin as a set of services or service-like subsystems, or it could begin as a modular monolith with strong internal boundaries and a single deployable application.

## Decision

CreatorOS will begin as a modular monolith.

Modules may be extracted into services later only if real operational requirements justify doing so.

## Rationale

The modular monolith model provides the best balance of simplicity, maintainability, and architectural discipline for the current stage of CreatorOS.

It allows the platform to preserve clear internal boundaries without incurring the operational cost of distributed systems too early. It keeps local development, testing, deployment, debugging, and refactoring simpler while the product model and workflow boundaries are still being validated.

This decision also aligns with the current scale of the platform. CreatorOS does not currently need multi-service deployment complexity, distributed tracing requirements, network-level failure handling between internal services, or the operational overhead of service coordination.

A modular monolith still supports good architecture. Internal modules can remain independent, testable, and replaceable so that future extraction is possible if it ever becomes necessary.

## Consequences

This decision requires strong internal discipline. A monolith without boundaries becomes a tightly coupled application, which CreatorOS explicitly is not intended to become. Module responsibilities, dependency rules, and orchestration boundaries must therefore be enforced consistently.

It also means the project can move faster in its early implementation without paying the cost of premature infrastructure. Deployment remains simpler, local development remains more approachable, and architectural iteration remains less expensive.

At the same time, the codebase must be structured so that future extraction remains possible. Business logic, persistence logic, provider integrations, and interfaces should remain separated rather than collapsing into convenience-based coupling.

## Future Considerations

If CreatorOS later develops real operational pressures such as independently scaling subsystems, distinct runtime environments, strong isolation needs, or organizational reasons for service separation, those requirements may justify selective extraction into services.

Such a change should be driven by observed operational needs, not by architectural fashion. Any move away from the modular monolith should be documented in a future ADR and should preserve the existing domain contracts and platform boundaries wherever possible.
