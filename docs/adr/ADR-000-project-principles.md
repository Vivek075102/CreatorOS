# ADR-000: CreatorOS Project Principles

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS is intended to be a long-lived software platform rather than a short-term automation project or a collection of disconnected workflows. Its architecture is expected to evolve over time, but that evolution should happen within a stable set of core values that protect the integrity, clarity, and long-term maintainability of the system.

Before making individual architectural decisions, the project should establish the principles that guide those decisions. Without explicit principles, future decisions may appear locally reasonable while gradually pulling the platform toward inconsistency, unnecessary complexity, or short-term convenience.

Future ADRs should inherit these principles rather than redefining them. Individual decisions may interpret these principles in specific contexts, but they should not contradict them without explicit discussion and documentation.

## Decision

Every architectural decision made in CreatorOS should align with the following principles.

### 1. Architecture Before Convenience

Never sacrifice architectural integrity for short-term speed.

### 2. Modularity First

Every module should have one responsibility and explicit boundaries.

### 3. Replaceability

External providers must always be replaceable.

Avoid vendor lock-in.

### 4. Explicit Contracts

Modules communicate through stable typed contracts rather than implicit assumptions.

### 5. Human Oversight

Automation should empower people rather than remove meaningful human control.

### 6. Long-Term Maintainability

CreatorOS should remain understandable years after implementation.

### 7. Evolution Without Rewrite

The platform should evolve through extension rather than repeated redesign.

### 8. Simplicity

Prefer the simplest architecture that satisfies current requirements.

Avoid premature complexity.

### 9. Testability

Every major component should be independently testable.

### 10. Documentation Is Part of the Product

Architecture, engineering standards, and operational knowledge are part of CreatorOS itself.

Documentation is not optional.

## Rationale

Establishing architectural principles before implementation improves consistency across decisions made at different times and by different contributors. It reduces technical debt by making tradeoffs explicit earlier, simplifies onboarding by giving new contributors a stable decision framework, and guides future architectural choices without requiring every ADR to restate the same foundations.

These principles are intentionally stable even while implementation evolves. The purpose of the principles is not to freeze the design of CreatorOS, but to ensure that growth happens in a way that remains coherent, maintainable, and aligned with the project's long-term purpose.

## Consequences

Future contributors should evaluate every proposed architectural change against these principles.

If a proposed direction violates one of these principles, that violation should trigger explicit discussion and a documented ADR rather than an implementation shortcut. The principles are meant to constrain decision-making in a productive way so that convenience does not silently override architectural intent.

## Future Considerations

These principles are expected to remain stable.

New principles may be added only when they represent fundamental architectural values rather than implementation preferences.
