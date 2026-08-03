# ADR-004: Human Approval and Level 4 Automation

- Status: Accepted
- Date: 2026-08-03

## Context

CreatorOS exists to reduce repetitive work while preserving creator control, quality, and strategic direction. The platform is intended to automate substantial parts of the content lifecycle, but it also operates in areas where output quality, brand alignment, publishing safety, and platform policy compliance matter.

This creates a central operating model decision: how autonomous CreatorOS should be by default. Fully manual workflows provide safety but limited leverage. Fully autonomous publishing provides maximum automation but carries greater quality, safety, and operational risk.

## Decision

CreatorOS targets Level 4 automation as its primary operating model.

Level 4 means end-to-end generation with publishing approval. The platform may automate research, content generation, asset production, workflow progression, and draft preparation, but publication remains gated by human review unless a future workflow is explicitly authorized otherwise.

## Rationale

Level 4 provides the best balance between leverage and oversight for the current goals of CreatorOS.

Human oversight remains essential because content quality, creator intent, platform compliance, and publication timing all carry meaningful consequences. A human approval checkpoint before publication reduces the risk of low-quality outputs, misaligned messaging, accidental policy violations, and unwanted uploads.

This decision also aligns with the documented philosophy of CreatorOS. The platform should empower creators, not replace them. Human review at key approval gates preserves accountability while still allowing substantial automation through the rest of the workflow.

## Consequences

This decision requires explicit approval gates in workflow design, especially around opportunity selection, script generation, storyboard generation, final render review, and publication.

It also means the platform must preserve visibility, audit history, resumability, and reviewable artifacts. Human approval only works well if the system makes decisions inspectable and produces structured outputs that can be reviewed without excessive manual reconstruction.

Level 4 automation may be slower than fully autonomous publication for some workflows, but that tradeoff is intentional at this stage of the platform.

## Future Considerations

Future Level 5 automation may be appropriate for explicitly authorized workflows if operational evidence shows that quality, safety, and control remain acceptable. Such workflows should be scoped intentionally and should not become the default implicitly.

Any move toward broader autonomous publishing should be documented in a future ADR and should include clear eligibility rules, safeguards, auditability, and rollback mechanisms.
