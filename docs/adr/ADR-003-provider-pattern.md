# ADR-003: Provider Pattern

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS depends on external systems for language models, research data, media generation, storage, publishing, and analytics. Those external services will change over time. Providers may improve, decline, change pricing, add constraints, remove features, or be replaced by better alternatives.

If CreatorOS were to integrate each vendor directly inside domain engines or application workflows, the platform would become tightly coupled to vendor-specific SDKs, response formats, and operational assumptions. That would increase change cost, reduce testability, and make long-term maintenance harder.

## Decision

CreatorOS will use provider abstractions rather than direct vendor integrations inside domain and application logic.

Concrete vendor implementations must be isolated behind stable internal interfaces.

## Rationale

The provider pattern preserves replaceability. CreatorOS is explicitly designed to remain independent of any single AI provider, publishing service, or infrastructure vendor. Stable provider interfaces make comparison, replacement, fallback, and coexistence practical.

The provider pattern also improves testing. When engines depend on abstract provider contracts rather than concrete SDKs, local tests, contract tests, and CI workflows can use fakes or mocks without requiring paid APIs or live network dependencies.

This decision also supports the pace of AI change. New providers will continue to appear, and existing providers will continue to evolve. CreatorOS needs an architecture that can absorb that volatility without forcing repeated redesign of domain and orchestration logic.

## Consequences

This decision requires additional interface design work up front. Inputs, outputs, error handling, usage accounting, and capability boundaries must be modeled carefully rather than delegated to external SDK conventions.

It also means provider implementations must translate external payloads into CreatorOS domain contracts. That translation layer is intentional. It protects the rest of the platform from vendor-specific drift.

The provider pattern does not eliminate all provider-specific behavior. Some capabilities will still require specialized implementation logic. However, those differences should remain isolated inside provider modules rather than spreading through the system.

## Future Considerations

As CreatorOS expands, provider routing may become more sophisticated and include fallback chains, capability-based selection, or quality and cost optimization rules. Those future improvements depend on having clean provider abstractions now.

If a future capability cannot fit cleanly into the existing provider model, the interface design should be revisited explicitly and documented through a future ADR rather than bypassed ad hoc in implementation.
