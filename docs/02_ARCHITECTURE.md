# CreatorOS Architecture

## 1. Purpose of This Document

This document defines the stable architectural boundaries, dependency rules, subsystem responsibilities, data flow, and extension model for CreatorOS.

Implementation details will evolve as the platform matures, new providers are added, and workflows become more capable. Those changes are expected. The architectural boundaries described here should remain stable so that the platform can grow without becoming fragile, tightly coupled, or difficult to understand.

This document is intentionally written at the system design level. It does not attempt to describe every implementation detail in the current repository. Instead, it establishes the target operating model that should guide future development decisions.

## 2. Architectural Objectives

CreatorOS is designed to satisfy the following architectural objectives:

- Modularity so that major capabilities can evolve independently.
- Provider independence so the platform is not locked to a single external service.
- Testability so core behavior can be validated without paid APIs or fragile environments.
- Observability so operators can understand what the system did, why it did it, and where it failed.
- Workflow resumability so long-running or multi-step jobs can recover from interruptions.
- Maintainability so the platform remains operable over the long term.
- Extensibility so new workflows, niches, providers, and publishing targets can be added safely.
- Human oversight so creators remain in control of quality, approval, and direction.
- Cost awareness so automation decisions remain economically responsible.
- Safe incremental automation so the system can move from manual control toward higher automation levels without losing trust or clarity.

## 3. System Context

CreatorOS initially serves one private creator producing faceless gaming content. The first publishing target is YouTube Shorts because it provides a clear operational scope for research, scripting, asset production, publication, and performance review.

That initial scope is deliberate, but it is not the architectural limit of the platform. Future support may include:

- Instagram Reels
- TikTok
- Facebook Reels
- X
- Long-form YouTube
- Multiple channels
- Multiple niches
- Multiple languages

CreatorOS is not currently being designed around multi-user SaaS requirements. Billing, tenant isolation, account management, and marketplace-style onboarding are not current architectural drivers and should not distort near-term design choices.

## 4. High-Level Architecture

CreatorOS is organized as a modular content operating system with the following major layers:

1. Interface Layer
2. Application and Orchestration Layer
3. Intelligence Layer
4. Content Domain Layer
5. Asset Production Layer
6. Publishing Layer
7. Analytics and Learning Layer
8. Provider Integration Layer
9. Persistence and Infrastructure Layer

The layers interact through explicit contracts rather than informal coupling.

```text
+-------------------------------+
|        Interface Layer        |
| CLI | n8n | API | UI | Sched. |
+---------------+---------------+
                |
                v
+-------------------------------+
| Application and Orchestration |
| jobs | workflow state | gates |
+---------------+---------------+
                |
                v
+-------------------------------+
|      Intelligence Layer       |
| research | script | quality   |
+---------------+---------------+
                |
                v
+-------------------------------+
|     Content Domain Layer      |
| typed contracts and entities  |
+-------+-----------+-----------+
        |           | 
        v           v
+---------------+   +----------------------+
| Asset         |   | Publishing Layer     |
| Production    |   | upload | schedule    |
| Layer         |   | reconciliation       |
+-------+-------+   +----------+-----------+
        |                      |
        +----------+-----------+
                   |
                   v
+-------------------------------+
| Analytics and Learning Layer  |
| analytics | experiments       |
+---------------+---------------+
                |
                v
+-------------------------------+
| Provider Integration Layer    |
| llm | media | storage | APIs  |
+---------------+---------------+
                |
                v
+-------------------------------+
| Persistence and Infrastructure|
| db | files | logs | secrets   |
+-------------------------------+
```

The diagram represents control flow, not a strict physical stack. Engines, asset services, publishing services, and analytics services may all use provider interfaces. Concrete provider implementations remain isolated behind those interfaces.

The direction of control should generally flow from interfaces into orchestration, then into domain-aware engines and supporting services. State, outputs, and observations may be persisted and analyzed across the full lifecycle.

## 5. Interface Layer

The Interface Layer contains the entry points through which users, schedulers, and external automation tools initiate CreatorOS use cases.

Expected interfaces include:

- CLI
- n8n workflows
- Future REST API
- Future dashboard
- Scheduled jobs

These interfaces are responsible for collecting inputs, triggering use cases, presenting status, and forwarding approvals or operator actions. They must not contain core business logic. Business rules belong in application services, engines, and domain modules where they can be tested, versioned, and reused across multiple interfaces.

## 6. Application and Orchestration Layer

The Application and Orchestration Layer coordinates end-to-end execution. It is responsible for:

- Pipeline orchestration
- Job creation
- Workflow state
- Step execution
- Retry handling
- Approval gates
- Resume after failure
- Idempotency
- Audit history

This layer converts incoming requests into structured jobs, selects the correct workflow definition, invokes the appropriate engines or services, records progress, and manages transitions between steps.

Two rules are mandatory:

Agents and engines must not call each other directly.

The orchestrator controls execution and passes structured data between components.

These rules keep cross-cutting workflow logic in one place, reduce hidden dependencies, and make resumption, retries, approvals, and observability practical.

## 7. Intelligence Layer

The Intelligence Layer contains the domain-specific engines that perform reasoning, generation, evaluation, and decision support. Each engine should expose a stable interface and accept structured inputs rather than ad hoc prompt fragments.

### Research Engine

Collects and normalizes signals from trend and research providers.

### Opportunity Engine

Ranks content opportunities using configurable scoring rules.

### Script Engine

Creates hooks, scripts, pacing, calls to action, and platform-aware narrative structures.

### Storyboard Engine

Transforms scripts into scenes, timing, visual instructions, and asset requirements.

### Metadata Engine

Generates titles, descriptions, hashtags, thumbnail concepts, and publishing metadata.

### Quality Engine

Evaluates generated outputs against configurable content, safety, branding, and production standards.

### Prompt Assets

Prompt definitions are version-controlled application assets rather than hidden strings inside provider adapters. They should be organized by engine and purpose, validated through typed contracts, and rendered through a dedicated prompt subsystem before any provider request is made.

The prompt subsystem is responsible for:

- Prompt definition contracts
- Prompt variable validation
- Prompt rendering
- Prompt registration and lookup
- Prompt asset loading
- Prompt asset discovery
- Prompt manifest validation

Prompt rendering belongs above the provider layer. Providers may adapt the rendered output to vendor-specific request formats, but they must not own the underlying task definition or prompt asset lifecycle.

Prompt assets remain outside the Python package in the repository `prompts/` directory. They are organized by category, use canonical versioned filenames, and may be described by a validated manifest that supports discovery and verification without becoming a persistence system or runtime database.

The initial real prompt catalog begins with research, script, and storyboard prompt assets for gaming workflows. Those assets are built into the repository, represented in the prompt manifest, and loadable into a fresh registry through platform-owned bootstrap functions rather than through provider adapters.

Application code should resolve prompts by stable logical name through the registry rather than by filesystem path. This keeps prompt selection inside platform-owned contracts even though the assets remain version-controlled files on disk.

An engine may internally coordinate focused agents, helper modules, or provider calls. External components should interact with the engine through a stable interface rather than reaching into its internal implementation details.

## 8. Content Domain Layer

The Content Domain Layer defines the structured objects that CreatorOS uses to exchange information across modules. These objects represent platform concepts rather than provider-specific payloads.

Key domain objects include:

- ContentOpportunity
- ContentBrief
- Script
- Storyboard
- Scene
- AssetRequest
- GeneratedAsset
- NarrationTrack
- EditedVideo
- PublishingPackage
- PublishedPost
- PerformanceReport
- LearningInsight
- ContentJob
- WorkflowStepResult

Modules should exchange typed data contracts rather than arbitrary text blobs whenever practical. Domain models should remain independent of provider-specific response formats so that providers can be replaced without changing the platform's conceptual model.

Domain contracts should support stable serialization for persistence, workflow handoff, audit history, and compatibility across process boundaries. Schema changes should be versioned or migrated when they affect stored workflow data.

## 9. Asset Production Layer

The Asset Production Layer is responsible for turning structured content plans into production assets. Its responsibilities include:

- Video generation
- Image generation
- Voice generation
- Music and sound handling
- Caption generation
- Thumbnail generation
- Editing and rendering
- Asset validation

This layer should use provider interfaces rather than concrete vendor APIs directly. Its outputs should be normalized into `GeneratedAsset` and related domain records so that downstream systems can operate consistently regardless of which provider or tool produced the asset.

## 10. Publishing Layer

The Publishing Layer is responsible for preparing and delivering content to external distribution platforms. Its responsibilities include:

- Platform-specific formatting
- Metadata validation
- Upload
- Scheduling
- Draft publication
- Final approval
- Publication status tracking
- Retry and reconciliation

Publishing should support both of the following operational modes:

- Level 4 automation with human approval
- Optional automatic publishing for explicitly authorized workflows

This layer must treat publication as a stateful, auditable operation. It should record attempts, detect duplicates, reconcile external platform state, and preserve enough history for diagnosis and recovery.

## 11. Analytics and Learning Layer

The Analytics and Learning Layer closes the feedback loop between published content and future workflow decisions. Its responsibilities include:

- Platform analytics ingestion
- Retention analysis
- CTR analysis
- Engagement analysis
- Content pattern analysis
- Experiment tracking
- Recommendations
- Feedback into future research and scripting

Analytics outputs must generate structured `LearningInsight` records.

The learning layer must not silently rewrite production prompts or configuration. Insights should be reviewed, tested, or activated through controlled experiments so that improvement remains visible, reversible, and measurable.

## 12. Provider Integration Layer

The Provider Integration Layer isolates external services from the rest of the system. Provider categories include:

- LLM providers
- Trend data providers
- Search providers
- Video providers
- Image providers
- TTS providers
- Music providers
- Storage providers
- Publishing providers
- Analytics providers

Stable internal interfaces should include types such as:

- `LLMProvider`
- `TrendProvider`
- `VideoProvider`
- `ImageProvider`
- `VoiceProvider`
- `StorageProvider`
- `PublishingProvider`
- `AnalyticsProvider`

Providers translate between CreatorOS domain contracts and external APIs. No domain engine should depend directly on OpenAI, Anthropic, Google, YouTube, ElevenLabs, or any other concrete service.

Prompts must remain provider-independent at the architecture level. A rendered prompt may later be passed to an `LLMProvider`, but prompt definitions, validation rules, and asset organization belong to CreatorOS rather than to any vendor SDK or provider implementation.

## 13. Provider Selection and Routing

Provider selection may consider:

- Capability
- Cost
- Reliability
- Latency
- Availability
- Output quality
- Platform policy
- Task type
- User preference

The initial release may use simple configuration-based selection. Future releases may support dynamic routing, fallback chains, provider scoring, or task-specific provider policies once there is enough operational evidence to justify the added complexity.

## 14. Persistence and Memory

CreatorOS should persist the structured information needed to operate, recover, audit, and improve. Key categories of stored information include:

- Jobs
- Workflow state
- Research results
- Opportunities
- Scripts
- Storyboards
- Assets
- Publications
- Analytics
- Experiments
- Learning insights
- Provider usage and cost
- Errors and retries

Prompts are not the system's memory. Persistent structured data is the system's memory.

PostgreSQL is the primary relational database for CreatorOS across development and production environments. It has been selected because it provides consistency between local development and production, strong relational modeling, transaction support, JSON and semi-structured data support where appropriate, indexing and query flexibility, concurrency support, a clear path for analytics and larger workloads, and reduced migration risk compared with starting on SQLite and changing later.

SQLite may still be used for isolated unit tests, temporary experiments, and narrowly scoped test fixtures. It must not be treated as the normal application database.

Database access must remain behind repository or persistence interfaces so that domain and application code are not coupled directly to PostgreSQL-specific behavior. PostgreSQL-specific features may be used intentionally within persistence implementations, but they must not leak into domain contracts unnecessarily.

## 15. Workflow Architecture

Workflows should be declarative where practical. A workflow definition should describe the sequence of work without forcing orchestration logic to be duplicated across interfaces or external automation tools.

Illustrative workflow examples include:

- Gaming Short
- Gaming Fact Short
- Gaming Lore Short
- Horror Story Short
- Long-form Gaming Video

A workflow definition should identify:

- Ordered steps
- Input and output contracts
- Required providers
- Retry policy
- Approval requirements
- Failure behavior
- Timeouts
- Cost limits

Python should contain domain logic, engine behavior, validation, and orchestration rules. n8n should coordinate schedules, approvals, notifications, and external workflow triggers.

Important rule:

Do not place critical business logic only inside n8n nodes.

## 16. Human Approval Model

CreatorOS should support configurable approval gates after:

- Opportunity selection
- Script generation
- Storyboard generation
- Final render
- Publishing package

The platform should recognize multiple automation levels:

- Level 0: Manual
- Level 1: AI generation with approval
- Level 2: Approved workflow automation
- Level 3: Mostly autonomous with exception handling
- Level 4: End-to-end generation with publishing approval
- Level 5: Fully autonomous publishing for explicitly authorized workflows

CreatorOS currently targets Level 4. That target reflects a design preference for strong human review at publication boundaries while still pursuing substantial operational leverage.

## 17. Error Handling and Resilience

CreatorOS should handle operational failures explicitly and predictably. Expectations include:

- Typed exceptions
- Retries with limits
- Exponential backoff
- Timeouts
- Provider fallback
- Partial failure recording
- Resume from last successful step
- Idempotent publishing actions
- Clear user-facing failure messages
- No silent failures

Resilience is not only a provider concern. Validation failures, workflow definition issues, approval rejections, and platform policy conflicts should also be represented clearly in system behavior and audit history.

## 18. Observability

CreatorOS should provide observability that makes job behavior understandable in production and during development. Relevant signals include:

- Structured logs
- Job IDs
- Step IDs
- Provider name
- Duration
- Token or usage counts
- Estimated cost
- Retry count
- Failure reason
- Output location

Secrets and private credentials must never be written to logs. Observability should support diagnosis, not create additional security risk.

## 19. Security and Secrets

CreatorOS should follow straightforward security practices appropriate for a private but production-quality platform:

- Secrets are loaded from environment variables.
- `.env` is never committed.
- External input must be validated.
- Provider responses are untrusted input.
- Publishing actions require explicit authorization.
- Credentials should be scoped to the minimum permissions required.
- Sensitive values must be redacted from logs.

Security design should be proportionate and practical. The goal is to prevent predictable operational mistakes without introducing unnecessary complexity.

## 20. Cost Management

CreatorOS should make cost visible and manageable. Relevant controls include:

- Provider usage tracking
- Per-job estimated cost
- Configurable limits
- Free or local provider preference where practical
- Approval before unusually expensive operations
- Cost versus quality measurement

Cost management is an architectural concern because provider selection, workflow depth, retry behavior, and quality thresholds all influence operating expense.

## 21. Plugin and Extension Model

CreatorOS should provide extension points for new:

- Niches
- Content formats
- Providers
- Publishing platforms
- Workflow definitions
- Scoring models
- Quality rules

Extensions should use documented interfaces and must not modify unrelated engines as a condition of integration. The platform should allow growth through clear extension seams without introducing a complex dynamic plugin marketplace prematurely.

The immediate goal is to build extension points, not a plugin economy.

## 22. Dependency Rules

The following rules are mandatory:

1. Interface modules may depend on application services.
2. Application services may depend on domain interfaces.
3. Domain models must not depend on concrete providers.
4. Engines must not import concrete provider implementations.
5. Providers may depend on external SDKs.
6. Provider SDK types must not leak into domain models.
7. Agents and engines must not call one another directly.
8. The orchestrator controls cross-engine execution.
9. Infrastructure code must not contain content strategy.
10. n8n must not be the only location of critical business logic.
11. No module may read secrets directly except through the configuration system.
12. Circular dependencies are prohibited.

## 23. Initial Repository Direction

The current repository already contains early platform folders such as `creatoros/`, `docs/`, `assets/`, `database/`, `prompts/`, and `workflows/`. Over time, the codebase should move toward a structure similar to the following without assuming that every directory already exists today:

```text
creatoros/
    cli.py
    config/
    core/
    domain/
    prompts/
    application/
    agents/
    engines/
    providers/
    workflows/
    infrastructure/
    observability/

tests/
    unit/
    integration/
    contract/
    end_to_end/

docs/
prompts/
assets/
database/
workflows/
```

Existing top-level prototype folders may be consolidated gradually and safely rather than moved without a migration plan. Architectural clarity matters, but stability during refactoring matters as well.

The intended persistence stack for CreatorOS is PostgreSQL, SQLAlchemy 2.x, Alembic, and Pydantic models at validation boundaries. This describes the selected architectural direction, not a claim that the full persistence schema or migration system is already implemented in the current repository.

The initial prompt foundation should treat prompt definitions as validated JSON assets loaded from the configured prompts directory, registered through a platform-owned registry, rendered through explicit typed variables, and discoverable through a manifest-aware asset structure. Broader asset formats or remote prompt management may be considered later only if they preserve the same architectural boundaries.

The current built-in prompt catalog is intentionally narrow. It covers the first provider-independent research, script, storyboard, thumbnail, and narration prompt assets plus local rendering support, not a complete prompt inventory for every engine or workflow. These assets define text-based output contracts only. Storyboard scene breakdown, visual direction, timing review, thumbnail concept generation, scene motion guidance, and narration direction are now represented as prompt contracts, but structured output parsing, real storyboard model generation, and downstream media-generation integration remain later milestone work.

## 24. Testing Architecture

CreatorOS should use multiple layers of testing:

- Unit tests for domain logic and engines
- Contract tests for provider implementations
- Integration tests for orchestration and persistence
- End-to-end tests for complete workflows
- Mock providers for local and CI testing
- No paid API required for normal unit tests

This testing model supports provider independence, faster feedback, and lower development cost while preserving confidence in workflow behavior.

## 25. Architectural Decision Process

Major architectural changes should be recorded in `docs/06_DECISIONS.md` or in individual ADR files under a documented decision-record pattern.

Examples of decisions that should be recorded include:

- Database choice
- Workflow engine choice
- Provider abstraction
- Queue system
- Storage platform
- API framework
- Deployment model

The purpose of these records is not bureaucracy. It is to preserve reasoning, clarify tradeoffs, and reduce repeated debate as the platform evolves.

## 26. Architectural Non-Goals

The current architecture does not attempt to provide:

- Multi-tenant SaaS
- Billing
- Marketplace
- Complex microservices
- Database clustering or sharding
- Complex high-availability database architecture
- Kubernetes
- Distributed event streaming
- Fully autonomous self-modifying prompts
- Premature scaling infrastructure

Selecting PostgreSQL as the primary database does not change these non-goals. PostgreSQL supports a production-quality relational foundation without implying premature distributed infrastructure or unnecessary operational complexity.

## 27. Evolution Strategy

CreatorOS should begin and remain, for now, a modular monolith.

Modules may later be extracted into services only when real operational requirements justify doing so. Those requirements might include independently scaling subsystems, isolated security boundaries, specialized runtime environments, or organizational constraints that cannot be served well inside one deployable system.

A modular monolith provides clear boundaries without the cost and complexity of premature microservices.

## 28. Final Architecture Principle

Everything should be replaceable except the architectural boundaries and domain contracts.

CreatorOS should remain simple enough for one person to understand today while being structured enough to grow into a larger platform tomorrow.
