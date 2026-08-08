# CreatorOS Engineering Standards

## 1. Purpose

This document defines the mandatory engineering standards for CreatorOS across code quality, testing, configuration, logging, security, documentation, dependency management, and Git practices.

These standards apply to both human-written and AI-generated code. Code origin does not change the standard of review, maintainability, safety, or correctness required for inclusion in the platform.

The purpose of these standards is to support long-term product quality while preserving development speed. They establish clear expectations so that changes remain understandable, testable, and consistent with the architecture of CreatorOS.

## 2. General Engineering Principles

The following principles are mandatory and should guide implementation decisions:

- Correctness before speed. A fast change that produces incorrect behavior is a defect, not a shortcut.
- Clarity before cleverness. Prefer code that another engineer can understand quickly over code that is compact but opaque.
- Simplicity before unnecessary abstraction. Abstractions should solve real duplication or stability problems, not hypothetical future needs.
- Maintainability before short-term convenience. Avoid decisions that save a few minutes now but make future changes fragile or expensive.
- Explicit behavior before hidden behavior. Inputs, outputs, side effects, and failure modes should be visible in the code structure.
- Small focused changes. Prefer changes that are easy to review, test, and reason about independently.
- Backward compatibility where stored workflow data is involved. Changes to persisted models, workflow state, or serialized contracts must account for compatibility or migration.
- Avoid premature optimization. Optimize when measurement or operational evidence justifies it.
- Avoid premature generalization. Do not design a framework when a well-structured implementation is sufficient.
- Build only what current requirements justify while preserving extension points. The platform should stay lean without blocking future expansion.

## 3. Supported Python Version

CreatorOS currently targets Python 3.12 or later.

Implementation should use supported standard-library functionality where practical before introducing additional dependencies. Python version changes must be intentional, tested, and documented because they affect local development, dependency compatibility, CI behavior, and deployment assumptions.

## 4. Code Organization

The following rules are mandatory:

- Each module must have one clear responsibility.
- Classes and functions must be cohesive and narrowly scoped.
- Circular imports are prohibited.
- Large utility dumping grounds are prohibited.
- Business logic must not live in CLI commands, n8n nodes, or provider adapters.
- Domain logic belongs in domain services and engines.
- Orchestration belongs in the application layer.
- Provider-specific logic belongs only in provider implementations.
- Infrastructure concerns must remain separate from content strategy.

Repository organization may evolve over time, but these boundaries must remain stable even when files move or modules are consolidated.

## 5. Naming Standards

CreatorOS uses the following naming conventions:

- `snake_case` for modules, functions, variables, and file names
- `PascalCase` for classes, protocols, enums, exceptions, and Pydantic models
- `UPPER_SNAKE_CASE` for constants
- Leading underscore for internal implementation details
- Clear descriptive names instead of abbreviations
- Boolean names beginning with `is_`, `has_`, `can_`, `should_`, or `enable_`
- Exceptions ending with `Error`
- Provider implementations named by capability and vendor where useful

Examples:

- `generate_storyboard`
- `ContentOpportunity`
- `DEFAULT_TIMEOUT_SECONDS`
- `_normalize_provider_response`
- `is_publishable`
- `OpenAITextProvider`

Names should reveal intent. If a name requires a comment to be understandable, the name should be improved first.

## 6. Type Hints

The following rules are mandatory:

- Public functions and methods must include type hints.
- Return types must be annotated.
- Modern Python syntax such as `str | None` and `list[str]` should be used.
- Replaceable components should use protocols or abstract interfaces where appropriate.
- `Any` should be avoided unless an integration boundary genuinely requires it.
- Untrusted provider data must be narrowed and validated before entering domain logic.
- Cross-module communication should use typed domain contracts.

Type hints improve design quality, documentation quality, and maintainability, but they do not replace runtime validation or defensive handling of untrusted inputs.

## 7. Data Models and Validation

Structured external or workflow data should use Pydantic models where appropriate.

The following rules are mandatory:

- Domain models must not contain provider SDK objects.
- External inputs and provider responses must be validated.
- Enums or constrained fields should be used where values are limited.
- Arbitrary dictionaries should be avoided when a stable contract is known.
- Serialization formats should remain stable.
- Stored schema changes require migration or compatibility planning.
- Models should reject invalid states early.

Validation should happen as close as practical to the boundary where data enters the system.

Structured text returned by AI providers must pass through a provider-independent parsing layer before becoming domain or application models. Normalization, field extraction, and model adaptation should happen in explicit parsing modules rather than through ad hoc string handling inside engines or providers.

When a prompt contract uses list-style sections, parsing logic must support only the documented syntax for that contract. CreatorOS currently supports simple bullet-list parsing for applicable research outputs and must not infer richer syntaxes that were not explicitly specified.

When a prompt contract uses repeating structured sections such as storyboard `SCENE_N` blocks, parsing should use the smallest dedicated safe block parser needed for that contract rather than flattening the structure into brittle ad hoc field handling.

## 8. Functions and Classes

Functions and classes must be designed for readability, reuse, and testability.

Mandatory rules:

- Functions should be small and focused.
- Inputs and outputs should be explicit.
- Side effects should be limited and visible.
- Dependencies should be passed explicitly rather than hidden in global state.
- Composition should be preferred over inheritance.
- Early returns may be used where they improve readability.
- Deeply nested control flow should be avoided.
- Overly broad base classes should be avoided.
- God objects and monolithic services are prohibited.

There is no arbitrary line limit for a function or class. If a function is difficult to understand, difficult to test, or difficult to name accurately, it should be decomposed.

## 9. Docstrings and Comments

Docstrings are required for:

- Public modules where purpose is not obvious
- Public classes
- Public functions and methods
- Complex internal behavior

Docstrings should describe intent, behavior, important constraints, parameters, return values, and raised exceptions where useful.

Comments should explain why, not restate what the code already says. Stale comments must be removed. `TODO` comments must include enough context to be actionable. Comments must not be used to compensate for confusing code that should be simplified instead.

## 10. Configuration and Secrets

The following rules are mandatory:

- All configuration must flow through the central settings system.
- Secrets must be loaded through environment variables.
- Hardcoded API keys, tokens, credentials, channel IDs, and private URLs are prohibited.
- `.env` must remain ignored by Git.
- `.env.example` must contain placeholders only.
- Configuration defaults must be safe for local development.
- Modules must not read `os.environ` directly outside the configuration layer.
- Configuration must be validated during startup.
- Sensitive values must not appear in exceptions or logs.

Configuration behavior must remain explicit and auditable. Hidden fallback behavior that changes production outcomes is not acceptable.

When a live provider smoke test is needed, it must be exposed through an explicit guarded path rather than through implicit startup behavior, normal workflow execution, or routine CLI commands. Local readiness checks must remain offline, and live smoke execution must require deliberate confirmation before any paid network request is attempted.

## 11. Logging and Observability

CreatorOS requires structured logging.

Logs should include relevant context such as:

- `job_id`
- `step_id`
- workflow name
- engine name
- provider name
- operation
- duration
- retry count
- output reference
- estimated usage or cost where available

Log level usage is mandatory:

- `DEBUG` for detailed development diagnostics
- `INFO` for normal lifecycle events
- `WARNING` for recoverable abnormal conditions
- `ERROR` for failed operations requiring attention
- `CRITICAL` for system-level failures preventing safe operation

Additional mandatory rules:

- `print` statements are prohibited in production modules.
- Secrets must never appear in logs.
- Full provider payloads must not be logged unless explicitly sanitized.
- Raw structured-output provider text must not be logged by default.
- Full rendered prompt contents should not be logged by default.
- Exceptions should preserve useful context.
- Logging failures must not hide the original error.
- API keys must never be printed back to the terminal, including in smoke-test or diagnostics commands.
- Safe operational usage metrics such as `input_tokens`, `output_tokens`, `total_tokens`, `cached_tokens`, and `reasoning_tokens` may be logged when available because they are usage counters rather than credentials.
- Secret-style token fields such as `access_token`, `refresh_token`, `auth_token`, and `bearer_token` must still be redacted.

## 12. Error Handling

CreatorOS requires explicit and disciplined error handling.

Mandatory rules:

- Use typed CreatorOS exceptions.
- Never use bare `except`.
- Catch exceptions only when the code can add context, recover, translate, or clean up.
- Preserve original exceptions through exception chaining.
- Keep clear boundaries between domain errors, provider errors, validation errors, and infrastructure errors.
- Silent failures are prohibited.
- Retry only transient failures.
- Validation failures and authorization failures must not be retried blindly.
- Network operations must use timeouts.
- User-facing errors must be understandable without exposing secrets.

Error handling should make failures easier to diagnose, not harder to observe.

## 13. Retry and Idempotency Standards

The following rules are mandatory:

- Retry attempts must be bounded.
- Exponential backoff should be used where appropriate.
- Retry policies should be configured by operation type.
- Publishing and other irreversible external actions must be idempotent.
- Attempts and external identifiers must be recorded.
- Duplicate uploads and duplicated paid generation must be avoided.
- Workflows should resume from the last confirmed successful state.
- An operation must not be retried when its prior result is uncertain without reconciliation.

The cost and side effects of each retry must be considered, not only the technical possibility of retrying.

## 14. Async and Concurrency

The following standards apply:

- Use asynchronous I/O where it provides a clear benefit for network-bound work.
- Do not make code asynchronous without a real need.
- Avoid blocking calls inside asynchronous code.
- Concurrency must have explicit limits.
- Shared state must be protected.
- Provider rate limits must be respected.
- Background tasks must expose status and failure information.
- Fire-and-forget execution is prohibited for critical work.

Concurrency should only be introduced when it improves throughput or responsiveness without reducing reliability or debuggability.

## 15. Dependency Management

The following rules are mandatory:

- Dependencies must be declared in `pyproject.toml`.
- Unrecorded manual dependencies are prohibited.
- The standard library should be preferred where practical.
- A package should be added only when it provides measurable value.
- Maintenance status, licensing, security, compatibility, and project health must be reviewed before adoption.
- Overlapping packages that solve the same problem should be avoided.
- Runtime and development dependencies must remain separated.
- Unused dependencies must be removed.
- Version constraints should balance reproducibility and maintainability.

Dependency growth should be treated as an architectural decision, not as a default response to implementation difficulty.

## 16. Provider Implementation Standards

Every provider implementation must:

- Implement a stable internal interface.
- Translate external data into CreatorOS domain contracts.
- Handle authentication through configuration.
- Use timeouts.
- Map external failures into typed provider errors.
- Record relevant usage and cost information.
- Avoid leaking SDK-specific types.
- Support mocking or test doubles.
- Document provider limitations.
- Avoid embedding content strategy inside the adapter.

Provider adapters exist to isolate external systems, not to become the primary location of business rules.

LLM providers must accept provider-independent request contracts and return normalized response contracts. They must not accept prompt-definition objects, must not resolve prompt registries internally, must not invoke parser registries, and must not log prompt or response content by default.

When a real vendor adapter is introduced, the same rules still apply. For example, the current OpenAI adapter may depend on the official OpenAI SDK internally, but it must keep SDK objects, raw transport payloads, authentication details, and vendor exception types inside the adapter boundary.

Application-layer execution orchestration belongs outside providers. CreatorOS now uses `LLMExecutionService` as the platform-owned path that resolves prompt definitions, renders variables, selects a registered provider, and resolves the typed parser registration. Agents and engines should eventually depend on that service boundary rather than duplicating prompt-to-provider-to-parser orchestration internally.

If a live provider verification path is added for development diagnostics, it must still use the same application-owned execution service and parser registry path rather than calling a vendor SDK directly from a CLI command, script, or engine.

Usage observability in the current milestone is limited to safe operational metadata such as normalized token counts and request identifiers. Monetary cost estimation, persistence of usage data, analytics storage, and dashboards remain future work.

The first migrated application agent now follows this rule directly. Research-agent code may call `LLMExecutionService`, but it must not call providers directly, must not load prompt files directly, must not invoke parser implementations directly, and must not branch on vendor-specific integrations such as OpenAI inside the agent module.

The same rule now also applies to script-agent integration. Script-agent code may call `LLMExecutionService`, but it must not call providers directly, must not invoke parser implementations directly, must not access `PromptRegistry` or `PromptRenderer` directly, and must not hardcode vendor-specific branches.

The same rule now also applies to storyboard-agent integration. Storyboard-agent code may call `LLMExecutionService`, but it must not call providers directly, must not invoke parser implementations directly, must not access `PromptRegistry` or `PromptRenderer` directly, and must not couple prompt execution to workflow state, asset generation, or publishing behavior.

The same rule now also applies to media-agent integration. Media-agent code may call `LLMExecutionService`, but it must not call image, video, voice, storage, or publishing providers directly, must not invoke parser implementations directly, must not access `PromptRegistry` or `PromptRenderer` directly, and must not turn planning outputs into generated assets inside the agent layer.

The same rule now also applies to review-agent integration. Review-agent code may call `LLMExecutionService`, but it must not call providers directly, must not invoke parser implementations directly, must not access `PromptRegistry` or `PromptRenderer` directly, and must not turn advisory review outputs into automatic revision, approval, workflow mutation, or publishing behavior inside the agent layer.

The same rule now also applies to integrated pipeline orchestration. `GamingContentPipeline` may coordinate migrated application agents, but it must not bypass them to call providers directly, must not invoke parser implementations directly, must not access `PromptRegistry` or `PromptRenderer` directly, and must stop before approval mutation or publishing behavior.

The same separation now also applies to future media execution. Media-generation providers may accept typed provider-neutral media requests and return typed provider-neutral results, but they must not contain content-planning logic, workflow mutation, publishing behavior, or vendor-specific assumptions in their calling code. The current mock media providers are deterministic contract implementations only, not real generators, and the first real `OpenAIImageProvider` must still keep OpenAI SDK objects, temporary provider URLs, and binary image payloads inside the adapter boundary.

The same rule applies to real speech adapters. `OpenAITTSProvider` may use the OpenAI speech SDK internally, but it must keep SDK objects, binary audio payloads, and transport details inside the adapter boundary, must not write files opportunistically, and must not misrepresent an estimated duration as provider-reported audio duration.

The same separation applies to rendering and composition work. Future `VideoProvider` implementations may generate clips, but final edited-output assembly belongs behind a separate render or composition boundary such as `RenderProvider`. Render providers must accept typed platform-owned composition contracts, must not embed workflow or publishing logic, and must not silently invoke FFmpeg, MoviePy, local file creation, or other heavyweight rendering side effects outside an explicitly approved milestone.

## 17. Prompt Engineering Standards

Prompts are version-controlled product assets.

The following rules are mandatory:

- Prompts must be stored outside provider adapters.
- Prompt templates must be organized by engine and purpose.
- Prompt definitions must remain provider-independent.
- Prompt asset directories must use lowercase snake_case category names.
- Prompt asset filenames must use the format `<name>.v<version>.json`.
- Prompt names should be globally unique enough to avoid registry collisions without relying on folder prefixes.
- Required inputs must be clear.
- Expected outputs should be structured.
- Behavior-changing prompt revisions should have versioning or change history.
- Secrets must never appear in prompts.
- Critical prompt formats should have tests or fixtures.
- Provider-specific formatting must remain isolated from the underlying task definition.
- Prompt changes must be reviewed like code changes.
- Production prompts must not be silently rewritten by analytics.
- Prompt assets loaded from disk must be validated before use.
- Initial prompt asset loading should use JSON files through the platform prompt loader unless a later ADR defines an expanded format strategy.
- The prompt manifest is descriptive and validated, not a runtime database.
- Prompt discovery checksums should be calculated from exact file bytes.
- Built-in prompt registration should occur through platform-owned bootstrap functions that validate the manifest before loading assets.
- CLI prompt inspection commands may expose prompt metadata safely, but full rendered prompt content should require an explicit operator action such as a dedicated flag.
- Prompt assets should rely only on supplied evidence and inputs. They must not imply browsing, hidden knowledge, or unsupported live awareness.
- Early prompt output contracts may remain text-based when a later milestone is expected to add structured parsing. That limitation must be documented explicitly rather than hidden behind fragile assumptions.
- The initial structured parsing foundation supports deterministic label/value text only. JSON parsing and Markdown-table parsing must not be implied until they are implemented and documented.
- Application code should resolve prompts by stable logical prompt name through the registry instead of hardcoding prompt file paths.
- Visual-direction prompt assets must remain provider-independent. They may describe composition, motion, overlays, and stylistic guidance, but they must not embed vendor-specific generation parameters or assume media has already been produced.
- Thumbnail, scene-visual, scene-motion, and narration-direction prompt assets must remain prompt-layer contracts only until dedicated media engines consume them. They must not imply that image, video, or voice providers were invoked during local rendering or manifest validation.
- Review prompt assets must remain advisory quality gates. They must use supplied evidence only, must not imply browsing or independent fact-checking, must not claim that content is approved for publication, and must not bypass the human approval model established by ADR-004.

Typed parsers for prompt outputs should be added incrementally by prompt family. The current parsing layer now covers the built-in research, script, storyboard, media-support, and review prompt outputs. Agent or workflow migration to consume those parsers must remain explicit future work rather than an implicit side effect of parser implementation.

When an application agent is migrated to typed prompt execution, it should accept normalized platform-owned input models, invoke stable logical prompt names through `LLMExecutionService`, and verify the returned typed output model explicitly. It must not inspect raw provider response text or couple itself to parser implementation details.

When script-generation agents are migrated, they should return typed parser output contracts first rather than collapsing directly into domain entities unless a separate explicit mapping layer is clearly owned at the application level. This keeps prompt-output contracts, domain entities, and workflow integration concerns decoupled while the migration pattern stabilizes.

When storyboard agents are migrated, they should return typed parser output contracts first rather than directly constructing media assets, edited timelines, or publishing-ready artifacts. Scene breakdown, timing review, and visual direction should remain explicit typed boundaries until a later application layer owns the mapping into storyboard domain entities or asset-production workflows.

When media-planning agents are migrated, they should return typed planning output contracts first rather than directly constructing generated assets, file paths, URLs, uploaded objects, or published media. Thumbnail concepts, scene visuals, scene motion, and narration direction should remain explicit typed planning boundaries until a later application layer owns the mapping into concrete media providers.

When review agents are migrated, they should return typed advisory review contracts first rather than directly constructing regenerated content, approval decisions, workflow-state transitions, or publishing actions. Script-quality, evidence-consistency, storyboard-quality, and publication-readiness reviews should remain explicit typed evaluation boundaries until a later application layer owns any human-reviewed downstream decisions.

When integrated content pipelines are added, they should coordinate only the minimum bounded set of agent calls required for a coherent package. They should prefer one economical happy path over broad prompt fan-out, and they must remain fail-fast until later milestones intentionally add retries, checkpoints, or resume behavior.

When media-provider foundations are added, they should reuse the shared provider registry and exception architecture where possible instead of creating parallel registries, hidden fallbacks, or capability-specific global state. Default provider selection belongs in configuration and explicit application composition, not inside provider implementations.

When a real image provider is added before storage or materialization services exist, the adapter must normalize results into safe provider-owned references rather than writing files opportunistically, exposing temporary signed URLs broadly, or retaining large base64 payloads in ordinary metadata.

When a real TTS provider is added before storage or materialization services exist, the adapter must normalize results into safe provider-owned references rather than writing audio files opportunistically, exposing raw binary payloads broadly, or retaining large audio blobs in ordinary metadata.

When a render-provider foundation is added before real rendering infrastructure exists, the initial implementation should stay contract-first. Deterministic mock rendering is acceptable for validating provider boundaries, request contracts, registry behavior, and service composition, but documentation and tests must state clearly that no binary video output, no FFmpeg execution, and no production render pipeline exist yet.

When a media-generation application service is added, it must remain a provider coordinator only. It may resolve providers, forward typed generation requests, and aggregate normalized generated-media results, but it must not execute prompts, import planning agents, invoke render providers, materialize files, upload assets, or mutate workflow state. Planning, generation, and rendering are separate stages and should remain independently testable.

When a final-assembly application service is added, it must remain a mapping and coordination layer only. It may accept typed storyboard and generated-media inputs, enforce deterministic scene-to-asset alignment, build a `ShortRenderRequest`, and delegate to `MediaRenderService`, but it must not call provider registries directly, generate images, generate narration, generate clips, invoke agents, execute prompts, write files, publish content, or silently repair invalid asset counts.

When a prompt output has a typed parser, it should be registered through a provider-independent parser registry using the same stable logical prompt name used by the prompt registry. Parser registration must declare the expected output model type explicitly, and builtin prompt/parser alignment should be validated through deterministic contract checks rather than informal assumptions.

Review parsers must remain advisory only. Parsing a decision such as `ready_for_human_review` must never publish content, approve content on behalf of a human, or mutate workflow state automatically.

Integrated content pipelines must preserve that same boundary. A positive publication-readiness result may indicate that a package is ready for human review, but it must not be reinterpreted as approval, scheduling authority, or publication completion.

When prompt execution reaches an LLM provider, the request should already be rendered into provider-independent messages. Providers should consume those rendered messages through a normalized request contract rather than reconstructing prompt definitions internally.

Parser selection after provider execution must be registry-driven. Application services must not branch on specific prompt names when selecting parsers, and they must not reach into parser implementation internals when `ParserRegistry` already provides the needed routing.

Prompt engineering is part of system design and must be handled with the same care as source code.

## 18. File and Asset Handling

The following rules are mandatory:

- Use `pathlib` for filesystem paths.
- Asset locations must be configurable.
- Output directories should be unique per job where practical.
- File types and extensions must be validated.
- Filenames must be safe.
- Code must not assume the current working directory.
- Atomic writes should be used where partial files would be dangerous.
- Temporary files must be cleaned reliably.
- Generated assets must be referenced through structured records.
- Valuable outputs must not be overwritten without explicit intent.

File and asset operations should preserve traceability, reproducibility, and recovery.

## 19. Database and Persistence Standards

PostgreSQL is the primary application database for CreatorOS.

The following rules are mandatory:

- Database access must occur through repositories or persistence services.
- SQLAlchemy 2.x should be used as the ORM and database toolkit.
- Alembic should be used for schema migrations.
- Application modules must not create ad hoc database connections.
- Database sessions and transactions must be managed through dedicated infrastructure or persistence services.
- PostgreSQL-specific types and queries must remain isolated to persistence implementations where practical.
- Domain models must not depend on SQLAlchemy models.
- SQLAlchemy models must not be passed directly across application boundaries.
- SQL must not be scattered through unrelated modules.
- Related state changes must use transactions.
- Schema changes require migrations.
- Migrations must be reviewed before execution.
- Destructive migrations require backups, explicit review, and a rollback or recovery plan.
- Timestamps must use UTC.
- Identifiers must be stable.
- Status values must be explicit.
- Audit fields should be included where operationally useful.
- Secrets must not be stored unnecessarily.
- Workflow history needed for resume and diagnosis must be preserved.
- Local development configuration must use a dedicated development database.
- Automated tests must use isolated test databases, temporary schemas, transactions, or controlled test containers.
- Production credentials must never be reused for development or tests.
- Tests must not depend on production data.

JSONB may be used when data is genuinely semi-structured, but it must not replace proper relational modeling by default. Indexes should be based on real query patterns rather than speculation.

Persistence is part of the operational contract of the platform and must be treated as a first-class design concern.

## 20. Testing Standards

CreatorOS uses the following test categories.

### Unit Tests

Unit tests cover pure domain logic, validation, scoring, and engine behavior with mocks where appropriate.

### Contract Tests

Contract tests verify that concrete providers obey internal interfaces and contract expectations.

### Integration Tests

Integration tests cover persistence, orchestration, configuration, and module collaboration.

### End-to-End Tests

End-to-end tests cover complete workflows using mock or sandbox providers.

The following rules are mandatory:

- Tests must be written with `pytest`.
- Tests must be deterministic.
- Paid APIs are prohibited in normal unit tests.
- Real publishing is prohibited in automated tests.
- Real OpenAI or other paid-provider calls are prohibited in automated tests. Use fake clients, fake services, or mock providers instead.
- Temporary storage and databases must be isolated.
- Test names must be descriptive.
- Arrange, Act, Assert structure should be used where practical.
- Success paths, edge cases, and failure behavior must be tested.
- Bug fixes should include regression tests.
- Tests should avoid implementation-detail coupling unless the behavior itself is the contract.
- Tests must not depend on execution order.

## 21. Test Doubles

CreatorOS should use test doubles intentionally:

- Fakes for lightweight functional replacements such as in-memory repositories or mock providers
- Stubs for fixed responses needed to drive a code path
- Mocks for verifying interactions where behavior depends on collaboration
- Spies for observing calls while preserving real behavior where useful

Stable fake providers are required for local development and CI. Excessive mocking of internal implementation details should be avoided because it makes tests brittle and obscures behavioral intent.

## 22. Code Quality Tools

The current project toolchain includes:

- Ruff for linting and formatting checks
- mypy for static type analysis
- pytest for tests

Expected commands are:

```text
python -m ruff check .
python -m mypy creatoros
python -m pytest
```

Tooling configuration belongs in `pyproject.toml`.

Current configuration indicates that mypy is enabled but not in strict mode. Standards and reviews should not claim strict mypy enforcement unless the project configuration is changed intentionally and documented.

## 23. Security Standards

The following rules are mandatory:

- Use least-privilege credentials.
- Validate inputs.
- Sanitize outputs where appropriate.
- Redact sensitive data.
- Maintain dependency security awareness.
- Require explicit authorization for publishing.
- Treat provider responses as untrusted input.
- Do not execute generated code or shell commands without strict validation and approval.
- Avoid unsafe deserialization.
- Protect temporary files and credential files.
- Security-sensitive changes require focused review.

Security decisions should match the risk of the action and the operational context of the platform.

## 24. Cost and Resource Standards

The following rules are mandatory:

- Record usage and cost where providers expose metrics.
- Apply limits to expensive operations.
- Avoid repeated asset generation when reusable results already exist.
- Cache only when correctness and freshness are preserved.
- Prefer mock, local, or free providers during development.
- Expensive operations must be visible to the operator.
- Retries must account for financial cost.
- Cost optimization must not silently reduce required quality.

Resource management includes money, rate limits, storage growth, and operator attention.

## 25. Git Standards

CreatorOS uses conventional-style commit prefixes:

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `chore`
- `build`
- `ci`
- `perf`

The following rules are mandatory:

- Commits must be small and meaningful.
- Commit messages must be clear and imperative.
- Never commit `.env`, credentials, generated large assets, caches, or virtual environments.
- Review `git diff` before committing.
- Run applicable tests before committing.
- Push after meaningful milestones.
- Avoid unrelated changes in the same commit.
- Do not rewrite shared history after pushing without explicit reason.

Examples:

- `feat: add workflow state repository abstraction`
- `fix: prevent duplicate publishing retries`
- `docs: clarify provider routing rules`

## 26. Branching and Review

The `main` branch should remain usable.

For larger work, use focused branch names such as:

- `feat/trend-engine`
- `feat/script-engine`
- `fix/provider-retry`
- `docs/architecture-update`

The following review checks are mandatory:

- Review generated diffs.
- Verify tests.
- Confirm no secrets are present.
- Confirm architecture boundaries are respected.
- Confirm documentation impact.
- Never approve code only because it was AI-generated or appears plausible.

## 27. AI-Generated Code Standards

AI-generated code must be treated exactly like human-written code.

Before acceptance, the following checks are mandatory:

- Inspect every changed file.
- Understand the behavior.
- Check architecture compliance.
- Run tests.
- Run lint and type checks.
- Verify no unrelated changes.
- Verify no invented dependencies.
- Verify no secrets or unsafe actions.
- Simplify unnecessarily complex generated code.
- Reject code that cannot be explained or maintained.

AI may assist implementation, but it does not own technical decisions. Accountability remains with the engineers who review, accept, and maintain the change.

## 28. Documentation Standards

The following rules are mandatory:

- Documentation must be updated when behavior, interfaces, configuration, or architecture changes.
- `README` instructions must be executable.
- Commands should target Windows CMD when documenting the primary local environment, while remaining portable where practical.
- Do not claim unimplemented features exist.
- Distinguish current behavior from future plans.
- Diagrams must remain readable in plain text or Markdown.
- Documentation must use stable terminology from the architecture.
- Obsolete instructions must be removed.

Documentation is part of the product surface for the engineering team and must be maintained with the same discipline as code.

## 29. Definition of Done

A change is complete only when the applicable items below have been satisfied:

- Requirements understood
- Architecture respected
- Code implemented
- Type hints present
- Validation added
- Errors handled
- Logging added
- Tests added or updated
- Tests pass
- Lint passes
- Type checks pass at the configured level
- Documentation updated
- No secrets included
- Diff reviewed
- Commit message prepared
- Change can be explained clearly

Not every documentation-only change requires every technical item above. However, all relevant items must be considered explicitly before a change is treated as done.

## 30. Prohibited Practices

The following practices are explicitly prohibited:

- Hardcoded secrets
- Bare `except`
- Silent failures
- Direct provider SDK usage in domain engines
- Circular imports
- Critical logic only in n8n
- Unbounded retries
- Production `print` statements
- Arbitrary dictionaries when stable typed contracts are available
- Hidden global mutable state
- Unapproved automatic publishing
- Paid API calls in unit tests
- Committing generated media files without a deliberate reason
- Self-modifying production prompts without controlled review
- Copying code without understanding its license or purpose

## 31. Final Standard

CreatorOS code should be understandable, testable, replaceable, observable, and safe to change.

The purpose of these standards is not to create bureaucracy. Their purpose is to preserve development speed by preventing avoidable complexity and technical debt.

## Technical Debt Policy

Technical debt is sometimes acceptable when it is:

- documented
- intentional
- time bounded
- tracked

Technical debt is not acceptable when it is:

- hidden
- repeatedly ignored
- undocumented
- used as a substitute for proper design

Every known architectural compromise should be recorded in:

docs/06_DECISIONS.md

or future ADR documents.

The objective is not to eliminate technical debt entirely.

The objective is to ensure it is visible, understood, and managed.
