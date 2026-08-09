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

For LLM execution specifically, the stable handoff should be:

`PromptRegistry -> PromptRenderer -> RenderedPrompt -> LLMRequest -> LLMProvider -> LLMResponse -> ParserRegistry -> typed CreatorOS output`

The provider boundary begins at `LLMRequest` and ends at `LLMResponse`. Providers should receive rendered provider-independent messages, not prompt definitions, prompt registries, or parser registries.

The application-layer orchestration point for that handoff is now `LLMExecutionService`. It resolves prompt definitions, renders them with validated variables, selects a registered LLM provider, executes the normalized request, and resolves the typed parser registration by stable logical prompt name. This keeps prompt selection, provider routing, and typed parsing in platform-owned application code rather than scattering that orchestration across agents, engines, or provider adapters.

The first application agent now uses that same platform-owned path directly. `GamingResearchAgent` depends on `LLMExecutionService`, invokes stable built-in research prompt names, and returns typed parsed research models without knowing anything about provider SDKs, prompt files, parser implementations, or raw provider text.

`GamingScriptAgent` now follows the same pattern for script-generation concerns. It depends on `LLMExecutionService`, invokes stable built-in script prompt names, and returns typed script parser outputs without direct provider calls, parser calls, prompt-registry access, filesystem prompt loading, or workflow mutation.

`GamingStoryboardAgent` now follows the same pattern for storyboard concerns. It depends on `LLMExecutionService`, invokes stable built-in storyboard prompt names, and returns typed storyboard parser outputs for scene breakdown, timing review, and visual direction without direct provider calls, parser calls, prompt-registry access, filesystem prompt loading, or workflow mutation.

`GamingMediaAgent` now follows the same pattern for media-planning concerns. It depends on `LLMExecutionService`, invokes stable built-in media prompt names, and returns typed media-planning parser outputs for thumbnail concepts, scene visuals, scene motion, and narration direction without direct provider calls, parser calls, prompt-registry access, filesystem prompt loading, or workflow mutation.

`GamingReviewAgent` now follows the same pattern for review concerns. It depends on `LLMExecutionService`, invokes stable built-in review prompt names, and returns typed review parser outputs for script quality, evidence consistency, storyboard quality, and publication readiness without direct provider calls, parser calls, prompt-registry access, filesystem prompt loading, workflow mutation, or publishing authority.

`GamingContentPipeline` now coordinates those five provider-independent application agents into one bounded pre-publication path. It begins from supplied research signals, uses the shared agent APIs rather than provider or parser internals, and stops after publication-readiness review. It does not perform web research, binary media generation, workflow approval mutation, or publishing.

Review and quality-control prompts are part of the prompt subsystem as advisory contracts, not as autonomous approval authorities. They may evaluate supplied artifacts for consistency, quality, and readiness signals, but they must not claim independent fact verification, platform approval, or publishing authority. Human approval remains authoritative under the Level 4 operating model.

The first integrated AI content pipeline currently uses one fixed happy-path sequence: trend discovery, opportunity evaluation, script generation, storyboard scene breakdown, thumbnail concept, narration direction, script-quality review, evidence-consistency review, storyboard-quality review, and publication-readiness review. That path is intentionally economical and bounded. It does not call keyword expansion, separate hook generation, separate CTA generation, storyboard timing review, storyboard visual-direction generation, or per-scene media prompts in this milestone.

Prompt assets remain outside the Python package in the repository `prompts/` directory. They are organized by category, use canonical versioned filenames, and may be described by a validated manifest that supports discovery and verification without becoming a persistence system or runtime database.

The initial real prompt catalog begins with research, script, and storyboard prompt assets for gaming workflows. Those assets are built into the repository, represented in the prompt manifest, and loadable into a fresh registry through platform-owned bootstrap functions rather than through provider adapters.

Application code should resolve prompts by stable logical name through the registry rather than by filesystem path. This keeps prompt selection inside platform-owned contracts even though the assets remain version-controlled files on disk.

### Structured Output Parsing

Structured parsing sits between provider responses and CreatorOS domain or application models. Provider text is untrusted input and must not flow directly into domain objects without normalization and validation.

The initial parsing foundation is provider-independent and accepts deterministic label/value structured text only. It is responsible for:

- Text normalization
- Canonical field-label normalization
- Structured field specification
- Safe multiline field extraction
- Simple bullet-list extraction for prompt contracts that explicitly use list sections
- Detection of missing required fields
- Detection of duplicate fields
- Handling of unknown fields according to explicit specification
- Safe adaptation into validated CreatorOS models

This parsing layer belongs above concrete providers and below domain-model construction. Providers may return text, but they must not decide how CreatorOS interprets platform-owned structured contracts.

The current typed parsers cover research, script, storyboard, media-support, and review outputs for the built-in gaming prompts. They remain provider-independent parsing adapters, not provider integrations, and they do not yet change agent or workflow execution.

Prompt registration and parser registration are separate architectural concerns. Prompt registries own prompt definitions, versions, and rendering lookup. Parser registries own the mapping from stable prompt logical names to typed parser callables and their declared output model types. This separation allows provider integration code to resolve parsing contracts without coupling prompt assets to parser implementation details or hardcoded agent branching.

The storyboard scene-breakdown contract uses a dedicated safe scene-block parser because it contains repeating `SCENE_N` sections that should not be forced through a brittle flat-field approximation.

Builtin prompt and parser registries should also support deterministic contract validation so the platform can detect drift between registered prompt assets and registered typed parsers before provider execution paths depend on them.

The current version intentionally does not include JSON parsing, Markdown-table parsing, automatic repair logic, retry-based self-correction, or workflow-state side effects from parser output. Review parsing remains advisory only. A parsed `ready_for_human_review` result is still not publication approval.

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

Public asset delivery is a separate concern from both local materialization and video generation. When a downstream provider requires a provider-reachable HTTPS asset reference, CreatorOS should use a provider-neutral asset-hosting boundary rather than coupling one media provider directly to one storage or CDN implementation.

This layer should use provider interfaces rather than concrete vendor APIs directly. Its outputs should be normalized into `GeneratedAsset` and related domain records so that downstream systems can operate consistently regardless of which provider or tool produced the asset.

Within this layer, AI video generation and final edited-output composition are separate concerns. A future `VideoProvider` may produce provider-owned clips from prompts or motion instructions, while a separate render or composition boundary is responsible for assembling prepared scene assets, narration references, captions, and transitions into a final Short. Those responsibilities should not be collapsed into one provider contract unless a later decision record explicitly changes that boundary.

Media planning is also separate from media execution. Planning agents may recommend thumbnail direction, scene visuals, motion ideas, and narration guidance, but a dedicated application service should translate those plans into typed media-generation requests and route them through provider interfaces. This keeps prompt execution, provider execution, and final rendering as distinct architectural stages.

CreatorOS now includes that next stage as a separate application boundary. `ShortAssemblyService` accepts typed storyboard output plus a generated-media package, aligns scene assets deterministically, builds a provider-neutral `ProductionTimeline`, wraps that result in a `ShortRenderRequest`, and delegates final composition through `MediaRenderService`. This keeps media generation, pacing, and final Short assembly distinct while proving that typed generated-media references can feed the render layer without introducing workflow, publishing, or storage coupling.

The provider-neutral clip-generation contract now also supports image-to-video inputs. `VideoGenerationRequest` may carry an optional `reference_image` represented as an existing `GeneratedAsset` with `asset_type=image`. That asset reference may point to either a local materialized file or a provider-owned transient URI, and later video adapters are responsible for translating the reference into the upload or fetch mechanism required by the concrete provider. CreatorOS does not add raw vendor request fields, raw filesystem path strings, or provider SDK objects to express this capability.

When a later adapter requires a public delivery URL instead of a local path or transient provider reference, CreatorOS should introduce that translation through a dedicated `AssetHostingProvider` boundary that returns a normalized `HostedAsset` contract. The hosting boundary should remain independent from any specific downstream video provider so implementations such as Cloudinary, S3, R2, or provider-native hosting can be replaced without changing the video-provider contract.

The first dedicated real video-provider shell is now `KlingVideoProvider`. It exists behind the same `VideoProvider` boundary as future providers such as Veo or later Kling variants, and it keeps provider-specific task submission, polling, and output retrieval inside the adapter boundary. CreatorOS continues to treat dedicated video providers as visual generation only. Narration remains owned by the TTS boundary, captions remain render instructions, and final composition remains owned by the render boundary.

The currently verified live Kling surface is intentionally narrow. CreatorOS now has an offline-tested HTTP transport for the documented Bearer-auth image-to-video create path at `https://api-singapore.klingai.com/image-to-video/kling-3.0-turbo`, using a fixed `1080p` resolution policy, integer durations from 3 through 15 seconds, and watermark disabled. That transport does not invent text-to-video endpoints, query-task paths, provider status enums, or success-output field shapes that have not yet been officially captured.

The same verified Kling image-to-video contract currently requires a provider-reachable first-frame URL. CreatorOS does not upload local files, publish temporary images, or introduce cloud storage just to satisfy that provider requirement in this phase. Local or ephemeral-only image references therefore remain a known integration limitation until a later explicitly designed storage or upload path exists.

CreatorOS now also includes a dedicated post-approval execution boundary above those services. `MediaExecutionPipeline` accepts an already completed `GamingContentPipelineResult` plus explicit human approval, verifies that the package is publication-ready, translates approved planning outputs into provider-neutral media-generation requests, materializes supported generated media into one run-scoped artifact workspace, and then coordinates `ShortAssemblyService` for final render execution. This preserves a mandatory two-phase architecture: planning stops at publication readiness, and media execution begins only through a second explicit call.

The current production pipeline still generates scene images and scene videos inside the same bounded media-generation package before local materialization. That is sufficient for text-to-video or provider-owned reference workflows, but it does not yet express a true dependency where generated scene images must complete before image-to-video clip requests are built from those exact outputs. The existing ephemeral `GeneratedImage.payload_bytes` transport is the preferred future handoff for adapters that can consume image bytes directly, but a later staged execution design will likely be required when scene-image generation must deterministically precede clip generation.

Paid asynchronous task providers introduce one additional invariant: CreatorOS may poll the same submitted provider task until it reaches a terminal state, but it must not silently resubmit a second paid generation request as an automatic retry when the first task is uncertain. That retry boundary belongs inside provider policy and must remain explicit.

CreatorOS now also includes a separate local artifact materialization boundary inside the Asset Production Layer. `ArtifactMaterializationService` converts supported provider-generated payloads into deterministic run-scoped local files under the configured `artifact_root`. This boundary exists to prepare controlled runtime inputs for later rendering stages. It is not a storage provider, not a publishing system, and not a cloud-asset abstraction.

The local artifact workspace is intentionally strict. Run identifiers are validated before path construction, destination paths must stay under the configured artifact root, MIME types map through an explicit allowlist to controlled extensions, filenames are sanitized for Windows-safe local use, and final writes use temporary files plus atomic replacement. Failed package materialization cleans up only the files created by that operation and leaves pre-existing files untouched.

Provider-generated binary payload transport remains ephemeral. Current generated media contracts may carry provider-neutral `payload_bytes` fields that are excluded from normal serialization and logging. Provider adapters may populate those bytes when safe local materialization is needed, but providers still must not write files themselves, store raw payloads in ordinary metadata, or leak vendor SDK objects beyond the adapter boundary.

CreatorOS now also includes its first real local renderer behind the existing `RenderProvider` contract. `FFmpegRenderProvider` consumes materialized local image, video, and optional narration files from the artifact workspace and produces a local MP4 in the same controlled workspace. This keeps the rendering boundary provider-driven while preserving the rule that rendering consumes platform-owned local files rather than provider-owned transient URLs.

The current render scope is intentionally narrow. Image scenes become timed segments, local video clips are normalized for composition, narration may be muxed as a bounded audio track, and the final output is a local H.264/AAC MP4. The production timeline remains authoritative: pacing is decided before rendering, captions are timed against that explicit timeline, and narration is reconciled to the approved Short duration rather than defining it. Shorter narration may end before visuals complete, while known narration that exceeds the approved duration fails safely before final render execution. Background music, overlays beyond captions, transitions beyond future intent, cloud rendering, and publishing remain outside this milestone.

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
- `TTSProvider`
- `RenderProvider`
- `VoiceProvider`
- `StorageProvider`
- `PublishingProvider`
- `AnalyticsProvider`

Providers translate between CreatorOS domain contracts and external APIs. No domain engine should depend directly on OpenAI, Anthropic, Google, YouTube, ElevenLabs, or any other concrete service.

CreatorOS now includes a first real OpenAI LLM adapter behind the provider boundary. That adapter exists to validate the architecture, not to collapse it. Agents, engines, prompts, and parsers must continue to interact only through the stable `LLMRequest`, `LLMResponse`, and `LLMProvider` contracts rather than through OpenAI SDK objects or vendor-specific request shapes.

Prompts must remain provider-independent at the architecture level. A rendered prompt may later be passed to an `LLMProvider`, but prompt definitions, validation rules, and asset organization belong to CreatorOS rather than to any vendor SDK or provider implementation.

When structured text is returned by a provider, the response should first pass through the provider-independent parsing layer before CreatorOS constructs downstream domain models. Raw provider text must not be treated as a trusted domain object.

Providers must not parse application outputs on behalf of CreatorOS. They return normalized provider responses only. ParserRegistry resolution, typed parsing, and workflow-level interpretation remain downstream platform responsibilities.

The current `LLMExecutionService` now owns that downstream prompt-to-provider-to-parser orchestration path at the application layer. It does not add retries, failover, repair logic, persistence, workflow mutation, or publication behavior. Those concerns remain separate future milestones.

CreatorOS now also has a dedicated application-layer `MediaGenerationService`. It owns provider selection and bounded execution for image generation, speech generation, and clip generation using the stable `ImageGenerationRequest`, `TTSGenerationRequest`, and `VideoGenerationRequest` contracts. It does not execute prompts, does not call planning agents, does not invoke the render boundary, and does not write files or upload artifacts. Its package-level output is a typed generated-media aggregate that can later feed the render layer.

CreatorOS now also has a dedicated application-layer `ArtifactMaterializationService`. It sits after provider execution and before any future real render backend that needs controlled local files. It owns artifact workspace creation, MIME allowlisting, safe filename derivation, atomic writes, and typed local artifact references. It does not call providers, does not invoke render services, does not upload to durable storage, and does not publish content.

CreatorOS now also has a real local render backend beneath `MediaRenderService`. `FFmpegRenderProvider` remains a provider adapter only: it resolves a local FFmpeg binary, validates local artifact paths under `artifact_root`, consumes the explicit provider-neutral production timeline carried by `ShortRenderRequest`, builds deterministic argv-based subprocess commands, applies typed timed caption overlays when present, fits optional narration to that authoritative timeline, and returns a normalized `RenderedVideo`. It does not generate media, execute prompts, access the network, or publish content.

Live OpenAI execution remains intentionally isolated from normal runtime paths. The current platform allows it only through an explicit guarded CLI smoke-test command that registers the OpenAI provider for one invocation, routes the request through `LLMExecutionService`, requires typed parser success, and refuses to run without a manual live-call confirmation flag. Agents, workflows, imports, health checks, and default runtime configuration remain mock-first and offline by default.

The same live-call safety rule now applies to post-approval short production. The current `run short` CLI entry point stays mock-first and offline by default, and any non-mock image or TTS provider selection must be acknowledged explicitly before execution. The render provider remains separate from that gate: local FFmpeg rendering is allowed without paid-media confirmation because it is a local subprocess backend rather than a paid external generation service.

Post-approval short production now also includes an explicit production preflight boundary. Before any media provider call, CreatorOS validates approval, run safety, output settings, provider registration, live-provider configuration, artifact-root usability, protected final-output collisions, and deterministic storyboard-to-media compatibility. This preflight is architecture-level validation rather than provider execution and must remain offline.

The same boundary now produces a typed deterministic execution plan before execution begins. That plan reports the effective providers, scene count, exact intended image/TTS/video call counts, whether live media would be used, the final output settings, and the run workspace path. It intentionally excludes secrets, prompt text, scripts, narration text, captions, and raw provider payloads.

The controlled `run short --plan` CLI path exposes that preflight and execution plan without generating media, materializing files, rendering video, or making network calls. This allows operators to review the exact intended live-call footprint before the first paid run while preserving the rule that `--confirm-live-calls` is still required on the later execution command itself.

Artifact semantics are now more explicit at the production boundary. Successful materialized artifacts are preserved when a later assembly or render stage fails so they remain available for diagnostics, while zero-byte or missing final render outputs are never treated as success. Automatic retry, failover, resume, checkpoint restart, publishing, and scheduling remain outside this milestone.

Structured observability for LLM execution may include safe operational usage metrics such as normalized token counts, request identifiers, provider names, models, durations, and parsed output model types. Those values are not treated as credentials. Secrets such as API keys, authorization values, access tokens, refresh tokens, client secrets, and credentials must still be redacted recursively, while rendered prompts, prompt variables, generated response text, and raw provider payloads remain excluded from normal logs.

Current agent migration is intentionally narrow. Research-agent execution can now operate through the provider-independent prompt-to-parser service boundary using supplied research signals only. Real `TrendProvider` or `SearchProvider` integration, web research, and broader workflow migration remain separate future milestones.

Script-agent migration is also intentionally narrow. Full script generation, hook generation, and CTA generation can now execute through the same provider-independent boundary using supplied inputs only, but that output is not yet wired into the orchestrator or production workflow path. Storyboard, media, and review agents remain separate future migration work.

Storyboard-agent migration is similarly narrow. Scene breakdown, timing review, and per-scene visual direction can now execute through the same provider-independent boundary using supplied inputs only, but this output is not yet wired into the orchestrator, media-generation pipeline, or production workflow path. Asset production, review-agent execution, and downstream publishing integration remain separate future milestones.

Media-agent migration is similarly narrow. Thumbnail concepts, scene visuals, scene motion, and narration direction can now execute through the same provider-independent boundary using supplied inputs only, but that output remains planning guidance rather than generated media. Image generation, video generation, voice synthesis, storage, and publishing remain outside this milestone, and the deterministic demo asset path stays separate.

Review-agent migration is similarly narrow. Script-quality, evidence-consistency, storyboard-quality, and publication-readiness reviews can now execute through the same provider-independent boundary using supplied inputs only, but those results remain typed advisory outputs. They do not regenerate content, mutate approval state, change workflow status, publish content, or replace human review. Cross-agent review pipelines and workflow integration remain later milestone work.

Integrated pipeline migration is similarly narrow. The new application pipeline can now coordinate the migrated research, script, storyboard, media-planning, and review agents into one pre-publication content package, but it remains fail-fast and stateless. It does not add retries, checkpoints, resume behavior, persistence, publishing, or approval-state mutation.

CreatorOS now also has a first provider-independent media provider foundation beneath that planning layer. Typed request and result contracts exist for image generation, speech/TTS generation, and video generation, and deterministic mock providers now satisfy those contracts through the existing generic provider registry. This establishes the future provider boundary for media execution without yet wiring binary media generation into the media-planning agent or the integrated content pipeline.

The first real media adapter is now the explicit `OpenAIImageProvider` registered under the stable image-provider name `openai-image`. It reuses the existing OpenAI credential path, translates the provider-neutral `ImageGenerationRequest` into the OpenAI images SDK interface, and normalizes results back into `GeneratedImage` without leaking SDK objects, temporary provider URLs, or raw image payloads across the adapter boundary. Mock remains the configured default, automated tests stay offline, and no current workflow invokes the real image adapter automatically.

The first real speech adapter is now the explicit `OpenAITTSProvider` registered under the stable voice-provider name `openai-tts`. It reuses the same OpenAI credential path, translates the provider-neutral `TTSGenerationRequest` into the OpenAI speech SDK interface, and normalizes results back into `GeneratedAudio` without leaking SDK objects or raw audio payloads across the adapter boundary. Mock remains the configured default, automated tests stay offline, and no current workflow invokes the real TTS adapter automatically.

Because later render stages require controlled local files rather than vendor-owned transient references, the generated image, audio, and video contracts may now carry provider-neutral ephemeral payload bytes. Those payload bytes are excluded from normal dumps and logs, exist only to support local runtime artifact materialization, and do not change the rule that provider adapters must not write files directly.

Provider SDK objects, raw transport payloads, and vendor-specific exception types must not escape the provider adapter boundary.

CreatorOS now also includes a separate provider-independent render/composition contract for final Short assembly. `VideoProvider` still represents future clip-generation work, while `RenderProvider` represents composition inputs such as timed scenes, prepared asset references, narration references, simple transition intent, caption overlay instructions, and minimal audio-composition policy. The current rendering milestone provides typed contracts, registry integration, a deterministic mock provider, a small application-layer `MediaRenderService`, and a real local FFmpeg adapter for offline MP4 composition. Caption rendering is still intentionally simple: scene-level overlays become deterministic timed subtitles with provider-neutral positioning, and the renderer does not generate or rewrite caption text. Narration handling is similarly narrow: the renderer may normalize one narration track to the final MP4 audio stream, but it does not synthesize narration, perform speech-to-text, or implement full multi-track sound design.

CreatorOS now also includes a thin application-layer `ShortAssemblyService` above that render boundary. It does not talk to provider registries, generation providers, agents, prompts, or parsers. Its job is only to convert typed storyboard scenes and `GeneratedMediaPackage` outputs into one deterministic `ShortRenderRequest`, preserve the distinction between thumbnail assets and timeline assets, build the provider-neutral production timeline that carries explicit scene pacing and caption alignment, and hand the result to `MediaRenderService`. In offline mode that still resolves to deterministic mock rendering. In local production mode the same contract can now flow into the FFmpeg adapter and produce a local MP4 under the same run-scoped workspace.

The new `MediaExecutionPipeline` sits above `MediaGenerationService`, `ArtifactMaterializationService`, and `ShortAssemblyService`, not beside or inside the planning agents. It does not rerun research, script, storyboard, media-planning, or review work. It consumes the already reviewed planning result as input, enforces explicit human approval, preserves one validated run ID across generated media, materialized files, and final render output, and keeps paid or side-effectful media work behind that approval boundary.

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
- Structured provider text must be parsed and validated before it becomes a CreatorOS model.
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

The current built-in prompt catalog is intentionally narrow. It covers the first provider-independent research, script, storyboard, thumbnail, narration, and review prompt assets plus local rendering support, not a complete prompt inventory for every engine or workflow. These assets define text-based output contracts only. The structured parsing foundation now validates deterministic label/value outputs before they are adapted into CreatorOS models, typed parser adapters now cover all current built-in prompt families, and a provider-independent parser registry now maps all 17 current built-in prompt logical names to typed output contracts. Research, script, storyboard, media-planning, and review agents now prove that those prompt families can execute through one shared application-owned boundary without direct provider or parser coupling, and the first integrated content pipeline now coordinates a bounded subset of those agent operations into one pre-publication package. Evidence consistency and publication-readiness review remain advisory prompt contracts that operate on supplied inputs only. Workflow integration for parsed outputs, actual media generation, review-driven revision flows, downstream media-production integration, and publishing remain later milestone work.

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
