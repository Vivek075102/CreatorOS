# CreatorOS

CreatorOS is a modular AI-powered gaming content factory.

## Current Phase

Phase 1 - Foundation

## Initial Goal

Build a reliable pipeline for trend research, script generation, and storyboarding.

## Environment Setup

1. Create the virtual environment.
2. Activate `.venv`.
3. Install project dependencies.
4. Run tests before committing changes.

## CLI

Use the CreatorOS CLI foundation to inspect configuration, mock providers, and workflow state behavior:

```bash
python -m creatoros --help
python -m creatoros config validate
python -m creatoros config show
python -m creatoros providers list --mock
python -m creatoros providers health --mock
python -m creatoros workflows transitions running
python -m creatoros workflows demo-state
python -m creatoros llm openai-check
```

Mock providers are local and free.
`workflows demo-state` demonstrates workflow state management only.
The first end-to-end content workflow remains deferred to Step 10.
`llm openai-check` is local-only and does not call OpenAI.

## First Executable Demo Workflow

Run the first local deterministic gaming workflow through the CLI:

```bash
python -m creatoros run gaming
python -m creatoros run gaming --approve
python -m creatoros run gaming --game Roblox --topic "funny myths" --approve
```

This workflow uses local deterministic mock providers only.
It performs no real trend research, creates no real media, and publishes only to a mock publishing provider.
Without `--approve`, it stops at the publishing approval gate.
Real provider integrations belong to later milestones.

## LLM Provider Foundation

CreatorOS now includes a provider-independent LLM execution boundary under `creatoros/providers`.

- Rendered prompt messages can be normalized into an `LLMRequest`.
- LLM providers return a normalized `LLMResponse` with optional `LLMUsage`.
- Providers receive `RenderedPrompt`-derived messages rather than prompt definitions or filesystem assets.
- ParserRegistry remains downstream of provider execution and is not invoked inside providers.
- Provider SDK objects must not escape provider adapters.
- Prompt text, rendered messages, and LLM response text are not logged by default by the provider foundation.
- The default provider and default model remain `mock` and `mock-model`.
- The deterministic mock LLM provider implements the new boundary without network calls and remains the default local development provider.
- A real `OpenAILLMProvider` adapter now exists behind the same provider-independent `LLMProvider` contract.
- The OpenAI adapter uses the official OpenAI Python SDK and the Responses API, but it is not wired into agents or workflows in this milestone.
- Normal automated tests continue to rely on deterministic fakes and do not require live API calls.

## LLM Execution Service

CreatorOS now includes an application-layer `LLMExecutionService` under `creatoros/services`.

- This service is the standard application boundary that connects `PromptRegistry`, `PromptRenderer`, `LLMProvider`, and `ParserRegistry`.
- The execution path is `PromptDefinition -> RenderedPrompt -> LLMRequest -> LLMResponse -> typed parsed output`.
- Parser selection is registry-driven by stable prompt logical name rather than hardcoded prompt branching.
- The service remains provider-independent and does not know OpenAI-specific request shapes or SDK objects.
- The default runtime remains `mock`, and OpenAI is used only when explicitly registered and selected.
- The current service does not add retries, response repair, failover, persistence, workflow-state updates, or publishing.
- Agents and workflows are not migrated to this service yet, but it is the intended application-layer entry point for future integration.
- Current tests prove complete offline end-to-end execution with both the mock provider and a fake OpenAI client without real network calls.
- Safe token-count usage metrics such as `input_tokens`, `output_tokens`, and `total_tokens` are operational observability fields, not credentials, and may appear in structured logs.
- Secret-style fields such as API keys, authorization values, access tokens, refresh tokens, client secrets, and credentials remain redacted in structured logs.
- Normal logs still exclude rendered prompt text, prompt variables, generated output text, raw provider payloads, and monetary cost calculations.

## Research Agent Integration

CreatorOS now includes a first application research agent that uses the provider-independent execution path directly:

- `GamingResearchAgent` depends on `LLMExecutionService` rather than calling providers, parsers, or prompt files directly.
- It currently supports typed research operations for `gaming_discover_trends`, `gaming_evaluate_opportunity`, and `gaming_expand_keywords`.
- The agent works only from supplied research signals and seed terms. It does not browse the web, call a real search provider, or perform live trend discovery.
- Mock remains the default provider path for normal execution and tests.
- Fake OpenAI agent tests prove that the same agent works through the OpenAI adapter without importing SDK types or changing agent logic.
- Script, storyboard, media, and review agents remain unmigrated in this milestone.

## Script Agent Integration

CreatorOS now also includes a provider-independent application script agent:

- `GamingScriptAgent` depends on `LLMExecutionService` rather than calling providers, parsers, prompt registries, or prompt files directly.
- It currently supports typed script operations for `youtube_shorts_script`, `gaming_hook`, and `gaming_cta`.
- The agent returns typed parser outputs such as `YouTubeShortsScriptOutput`, `GamingHookOutput`, and `GamingCTAOutput` rather than prematurely collapsing them into domain `Script` entities.
- Mock remains the default provider path for normal execution and tests.
- Fake OpenAI script-agent tests prove that the same agent works unchanged through the OpenAI adapter without live API calls.
- The script agent is not yet wired into the production workflow or orchestrator path.
- Storyboard, media, and review agents remain unmigrated in this milestone.

## Storyboard Agent Integration

CreatorOS now also includes a provider-independent application storyboard agent:

- `GamingStoryboardAgent` depends on `LLMExecutionService` rather than calling providers, parsers, prompt registries, or prompt files directly.
- It currently supports typed storyboard operations for `storyboard_scene_breakdown`, `storyboard_timing_review`, and `storyboard_visual_direction`.
- The agent returns typed parser outputs such as `StoryboardSceneBreakdownOutput`, `StoryboardTimingReviewOutput`, and `StoryboardVisualDirectionOutput` rather than prematurely collapsing them into domain storyboard entities or media-generation work.
- `GamingStoryboardSceneBreakdownRequest.from_script(...)` provides a stable bridge from typed script output into storyboard scene-breakdown input without introducing workflow coupling.
- Mock remains the default provider path for normal execution and tests.
- Fake OpenAI storyboard-agent tests prove that the same agent works unchanged through the OpenAI adapter without live API calls.
- The storyboard agent is not yet wired into the production workflow or orchestrator path.
- Media-generation, asset-production, and review-agent integration remain later milestones.

## Media Agent Integration

CreatorOS now also includes a provider-independent application media-planning agent:

- `GamingMediaAgent` depends on `LLMExecutionService` rather than calling providers, parsers, prompt registries, or prompt files directly.
- It currently supports typed media-planning operations for `gaming_thumbnail_concept`, `gaming_scene_visual_prompt`, `gaming_scene_motion_prompt`, and `gaming_narration_direction`.
- The agent returns typed planning outputs such as `GamingThumbnailConceptOutput`, `GamingSceneVisualOutput`, `GamingSceneMotionOutput`, and `GamingNarrationDirectionOutput`.
- These outputs are planning instructions only. They are not generated images, videos, narration files, uploaded assets, or published media.
- Mock remains the default provider path for normal execution and tests.
- Fake OpenAI media-agent tests prove that the same agent works unchanged through the OpenAI adapter without live API calls.
- The existing deterministic `DemoAssetAgent` remains in place for the demo workflow and still uses mock media providers to produce demo asset contracts.
- `GamingMediaAgent` is not yet wired into the production workflow or orchestrator path.
- Real image, video, narration, storage, and publishing provider integration remain later milestones.

## Review Agent Integration

CreatorOS now also includes a provider-independent application review agent:

- `GamingReviewAgent` depends on `LLMExecutionService` rather than calling providers, parsers, prompt registries, or prompt files directly.
- It currently supports typed review operations for `gaming_script_quality_review`, `gaming_evidence_consistency_review`, `gaming_storyboard_quality_review`, and `gaming_publication_readiness_review`.
- The agent returns typed advisory outputs such as `GamingScriptQualityReviewOutput`, `GamingEvidenceConsistencyReviewOutput`, `GamingStoryboardQualityReviewOutput`, and `GamingPublicationReadinessReviewOutput`.
- Review outputs are advisory only. They do not automatically revise content, approve workflow state, publish content, schedule anything, or generate media.
- `GamingScriptQualityReviewRequest.from_script(...)`, `GamingStoryboardQualityReviewRequest.from_storyboard(...)`, and `GamingPublicationReadinessReviewRequest.from_review_inputs(...)` provide explicit typed bridges from upstream agent outputs without introducing workflow coupling.
- Mock remains the default provider path for normal execution and tests.
- Fake OpenAI review-agent tests prove that the same agent works unchanged through the OpenAI adapter without live API calls.
- Human approval remains mandatory, and broader cross-agent pipeline integration remains a later milestone.

## Integrated AI Content Pipeline

CreatorOS now also includes a first integrated provider-independent AI content pipeline:

- `GamingContentPipeline` coordinates the existing `GamingResearchAgent`, `GamingScriptAgent`, `GamingStoryboardAgent`, `GamingMediaAgent`, and `GamingReviewAgent`.
- The pipeline begins from supplied research signals only. It does not browse the web and does not call a live trend or search provider.
- The happy-path stage order is fixed: trend discovery, opportunity evaluation, script generation, storyboard scene breakdown, thumbnail concept, narration direction, script-quality review, evidence-consistency review, storyboard-quality review, publication-readiness review.
- The current happy path makes 10 bounded LLM calls. It intentionally does not call keyword expansion, separate hook generation, separate CTA generation, storyboard timing review, storyboard visual-direction generation, or per-scene media prompts.
- The media stage produces planning outputs only. It does not generate binary media, upload assets, or publish anything.
- Review outputs remain advisory only. They do not automatically revise content, approve workflow state, or schedule publication.
- Publication readiness is not human approval. The pipeline always stops after publication-readiness review and returns a typed pre-publication package for later human review.
- Failures are fail-fast. The pipeline does not add retries, failover, checkpoint persistence, or resume behavior in this milestone.
- The existing deterministic demo `GamingWorkflowOrchestrator` remains in place unchanged alongside this new application pipeline.

## Media Provider Foundation

CreatorOS now also includes a provider-independent media provider foundation for future generation work:

- Separate typed provider-neutral request and result contracts now exist for image generation, speech/TTS generation, and video generation.
- The current capability-specific contracts are `ImageProvider`, `TTSProvider`, and `VideoProvider`, with the existing `VoiceProvider` kept as a backward-compatible compatibility contract for the deterministic demo path.
- The shared `ProviderRegistry` is reused for media providers. No second provider framework was introduced.
- Default provider settings now include `default_image_provider`, `default_tts_provider`, and `default_video_provider`, each defaulting to `mock`.
- The first real image adapter is now `OpenAIImageProvider`, registered explicitly under the stable image provider name `openai-image`.
- `OPENAI_API_KEY` is reused for the OpenAI image adapter, and `DEFAULT_IMAGE_MODEL` must be configured explicitly before any live image request can succeed.
- Deterministic `MockImageProvider`, `MockTTSProvider`, and `MockVideoProvider` now return typed mock generation results without network calls, binary media generation, FFmpeg, file output, or vendor SDKs.
- Mock remains the default image provider. Real OpenAI image generation is opt-in only and is not invoked automatically by `GamingMediaAgent`, the integrated content pipeline, or automated tests.
- OpenAI SDK client objects, temporary provider URLs, and binary image payloads remain inside the adapter boundary. No image files, storage uploads, or permanent asset materialization are created in this milestone.
- Capability-specific mock registry helpers now exist for image, TTS, and video provider setup in addition to the existing full mock registry bootstrap.
- `GamingMediaAgent` remains planning-only and does not call these providers yet.
- `GamingContentPipeline` remains unchanged in responsibility and still stops at the pre-publication human-review boundary.
- Real speech and video providers remain later milestones, and a guarded live image smoke command is still deferred.

## Controlled OpenAI Smoke Test

CreatorOS now includes one explicit opt-in CLI path for a controlled live OpenAI smoke test:

```bash
python -m creatoros llm openai-check
python -m creatoros llm openai-smoke --model gpt-5-mini --confirm-live-call
python -m creatoros llm openai-smoke --model gpt-5-mini --game Roblox --topic "funny myths" --platform youtube_shorts --tone natural --confirm-live-call
```

- `openai-check` is local-only. It reports whether an API key and non-mock model are configured for a future live smoke run.
- `openai-smoke` is the only current CLI command allowed to make a live OpenAI request, and it refuses to run without `--confirm-live-call`.
- The smoke path uses the existing `gaming_cta` builtin prompt, the provider registry, `LLMExecutionService`, and the typed `GamingCTAOutput` parser result.
- The command does not print prompt contents, raw SDK payloads, or secrets.
- Automated tests continue to use fake providers and fake clients only. They do not make real OpenAI calls.
- Agents, workflows, and the default runtime remain mock-first until later migration milestones.

## Prompt Foundation

CreatorOS now includes a provider-independent prompt-system foundation under `creatoros/prompts`.

- Prompt definitions are validated through typed Pydantic contracts.
- Prompt rendering uses explicit variables rather than ad hoc string assembly.
- Prompt definitions can be registered and resolved through a platform-owned registry.
- Prompt assets can be loaded from the configured prompts directory as validated JSON files.
- Prompt assets are organized under the repository `prompts/` directory by category.
- Prompt asset filenames use the format `<name>.v<version>.json`.
- `prompts/manifest.json` is a descriptive, validated manifest for discovery and verification rather than a runtime database.
- Prompt discovery calculates SHA-256 checksums from exact file bytes.

This foundation does not claim that production prompt catalogs, real LLM workflows, or remote prompt management are already complete. It establishes the architectural base for those later milestones.

## Structured Parsing Foundation

CreatorOS now includes a provider-independent structured-output parsing foundation under `creatoros/parsing`.

- Structured parsing sits between untrusted provider text and CreatorOS domain or application models.
- Provider text must not flow directly into domain objects without normalization and validation.
- The parsing layer is provider-independent and does not integrate any real LLM vendor in this milestone.
- The current v1 parser supports deterministic label/value structured text only.
- Research prompt outputs now have typed parsers for trend discovery, opportunity evaluation, and keyword expansion.
- Script prompt outputs now have typed parsers for YouTube Shorts scripts, gaming hooks, and gaming CTAs.
- Storyboard prompt outputs now have typed parsers for scene breakdowns, visual direction, and timing review.
- Media prompt outputs now have typed parsers for thumbnail concepts, scene visuals, scene motion, and narration direction.
- Review prompt outputs now have typed advisory parsers for script, evidence, storyboard, and publication-readiness reviews.
- A `ParserRegistry` now maps stable logical prompt names to typed parser registrations.
- Each parser registration declares its expected output model type explicitly.
- Prompt registration and parser registration remain separate concerns.
- Builtin prompt/parser contract validation detects drift between prompt assets and typed parser registrations.
- All 17 current builtin prompt assets now have typed parser registrations.
- Keyword-list parsing supports simple `- item` bullet syntax only.
- Repeating storyboard scenes use a dedicated safe scene-block parser rather than a brittle flat-field approximation.
- JSON parsing is not part of this milestone.
- Markdown-table parsing is not part of this milestone.
- Raw LLM responses must not be logged by default by the parsing layer.
- No repair or retry mechanism exists yet.

Agents and workflows are not yet migrated to consume these typed parsers automatically. Review outputs remain advisory only, and `ready_for_human_review` is not publication approval.
Provider integration can now resolve typed parsers through a provider-independent registry contract instead of hardcoded prompt-family branching. A real OpenAI adapter now exists behind the provider boundary, and an application-layer `LLMExecutionService` now connects prompt rendering, provider execution, and parser resolution without changing workflow behavior. The default runtime still stays on the local mock provider.

## Prompt Asset Structure

The current prompt repository structure is:

```text
prompts/
    manifest.json
    research/
        gaming/
        common/
    script/
    storyboard/
    narration/
    thumbnail/
    metadata/
    review/
    publishing/
```

Prompt names are global logical identifiers and should be unique enough to avoid collisions without relying on folder prefixes. The manifest supports validation and inventory, but CreatorOS does not automatically register prompt assets from the manifest at runtime yet.

## Built-In Research Prompts

CreatorOS now includes a first set of built-in provider-independent prompt assets for gaming workflows:

- `gaming_cta`
- `gaming_discover_trends`
- `gaming_evaluate_opportunity`
- `gaming_expand_keywords`
- `gaming_hook`
- `storyboard_scene_breakdown`
- `storyboard_timing_review`
- `storyboard_visual_direction`
- `youtube_shorts_script`

These prompts are stored as validated JSON assets under `prompts/research/gaming/`, `prompts/script/`, and `prompts/storyboard/`, represented in `prompts/manifest.json`, and loadable through the platform prompt registry without provider calls. Stable logical prompt names should be used from application code instead of filesystem paths.

CreatorOS also now includes provider-independent media-support prompt assets for:

- `gaming_thumbnail_concept`
- `gaming_scene_visual_prompt`
- `gaming_scene_motion_prompt`
- `gaming_narration_direction`

These media-support prompts remain local prompt assets only. They do not invoke image generation, video generation, or narration providers, and they do not imply that downstream media engines have already been implemented.

CreatorOS also includes provider-independent review prompt assets for:

- `gaming_script_quality_review`
- `gaming_evidence_consistency_review`
- `gaming_storyboard_quality_review`
- `gaming_publication_readiness_review`

These review prompts are advisory quality gates only. They use supplied inputs only, do not browse, do not independently fact-check, do not publish, and do not bypass the human approval model.

Use the CLI to inspect the manifest, discover assets, list registered prompts, and render the deterministic research prompt locally:

```bash
python -m creatoros prompts manifest show
python -m creatoros prompts manifest validate
python -m creatoros prompts discover
python -m creatoros prompts list
python -m creatoros parsers list
python -m creatoros parsers validate
python -m creatoros prompts render gaming_discover_trends
python -m creatoros prompts render gaming_discover_trends --game Roblox --topic "funny myths" --signals "Players are discussing recurring myths about game mechanics." --show-content
python -m creatoros prompts render youtube_shorts_script
python -m creatoros prompts render youtube_shorts_script --title "Roblox: Funny Myths" --game Roblox --topic "funny myths" --angle "test three popular myths" --hook-direction "challenge a common belief" --source-summary "Supplied research notes discuss recurring myths about game mechanics." --show-content
python -m creatoros prompts render gaming_hook --show-content
python -m creatoros prompts render gaming_cta --show-content
python -m creatoros prompts render storyboard_scene_breakdown
python -m creatoros prompts render storyboard_scene_breakdown --title "Roblox: Funny Myths" --game Roblox --hook "You probably still believe this Roblox myth." --body "Players often repeat three myths about game mechanics." --ending "Now you know which claims deserve checking." --call-to-action "Which myth should we test next?" --duration 30 --show-content
python -m creatoros prompts render storyboard_visual_direction --show-content
python -m creatoros prompts render storyboard_timing_review --show-content
python -m creatoros prompts render gaming_thumbnail_concept --show-content
python -m creatoros prompts render gaming_scene_visual_prompt --show-content
python -m creatoros prompts render gaming_scene_motion_prompt --show-content
python -m creatoros prompts render gaming_narration_direction --show-content
```

By default, `prompts render` shows prompt metadata only. Full rendered prompt content is shown only when `--show-content` is provided. These commands render locally, do not call an LLM provider, and do not imply that real AI generation is already wired into the demo workflow.

The current research, script, storyboard, thumbnail, narration, and review prompt output contracts are text-based. All current prompt families now have typed provider-independent parsing support, but parser output still does not change workflow state automatically. Review prompts remain advisory and publication readiness means ready for human review, not approved for publication. Workflow integration for parsed outputs, real image generation, real video generation, real narration generation, and downstream media-production integration will be added in later milestones.
