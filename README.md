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

## Runtime Artifact Workspace

CreatorOS now includes a local runtime artifact materialization layer for provider-generated media.

- `ARTIFACT_ROOT` defaults to the repository-local `artifacts/` directory and can be overridden through the settings system.
- `ArtifactMaterializationService` is the only current application service that turns supported media payloads into local files.
- Workspaces are deterministic and run-scoped, for example `artifacts/run_001/images/`, `artifacts/run_001/audio/`, and `artifacts/run_001/video/`.
- Filenames are sanitized, MIME types are allowlisted, path traversal is rejected, and writes use a temporary file plus `os.replace` for atomic finalization.
- Raw payload bytes remain ephemeral on generated media contracts and are excluded from normal serialization and logging.
- Provider adapters still do not write files directly, and the artifact workspace now feeds the local FFmpeg render path without adding cloud storage or publishing.

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
- `VideoGenerationRequest` now supports both text-to-video and provider-neutral image-to-video requests through an optional `reference_image` asset reference.
- CreatorOS now also includes a provider-neutral `AssetHostingProvider` contract plus `AssetHostingService` for future public HTTPS asset delivery when a downstream provider cannot read local files.
- The first real hosting implementation is `CloudinaryAssetHostingProvider`, but Cloudinary remains an optional adapter rather than an architectural dependency of Kling or any other media provider.
- Hosted assets normalize into a dedicated `HostedAsset` contract so public delivery references remain distinct from local generated or materialized assets.
- The first real dedicated video-provider shell is now `KlingVideoProvider`, and the verified Kling 3.0 Turbo image-to-video create-task HTTP transport now exists behind it, but live polling remains intentionally gated until the official query-task path and result schema are captured.
- The current capability-specific contracts are `ImageProvider`, `TTSProvider`, and `VideoProvider`, with the existing `VoiceProvider` kept as a backward-compatible compatibility contract for the deterministic demo path.
- The shared `ProviderRegistry` is reused for media providers. No second provider framework was introduced.
- Default provider settings now include `default_image_provider`, `default_tts_provider`, and `default_video_provider`, each defaulting to `mock`.
- The first real image adapter is now `OpenAIImageProvider`, registered explicitly under the stable image provider name `openai-image`.
- `OPENAI_API_KEY` is reused for the OpenAI image adapter, and `DEFAULT_IMAGE_MODEL` must be configured explicitly before any live image request can succeed.
- The first real TTS adapter is now `OpenAITTSProvider`, registered explicitly under the stable speech provider name `openai-tts`.
- `OPENAI_API_KEY` is reused for the OpenAI TTS adapter, and `DEFAULT_TTS_MODEL` must be configured explicitly before any live TTS request can succeed.
- Deterministic `MockImageProvider`, `MockTTSProvider`, and `MockVideoProvider` now return typed mock generation results without network calls, binary media generation, FFmpeg, file output, or vendor SDKs.
- The image-to-video request path uses the existing `GeneratedAsset` abstraction rather than a raw path string, so future dedicated video providers remain replaceable.
- The current verified Kling API contract uses one Bearer API key, the host `https://api-singapore.klingai.com`, the create path `/image-to-video/kling-3.0-turbo`, a fixed `1080p` resolution policy, integer durations from 3 through 15 seconds, and watermark disabled.
- The current verified Kling image-to-video contract requires a provider-reachable first-frame URL. CreatorOS does not upload or host local images for Kling in this phase.
- Cloudinary hosting currently supports local image assets only, produces HTTPS delivery URLs, uses deterministic run-scoped public IDs, and exposes explicit delete support for later post-Kling cleanup orchestration.
- Hosting remains a visible network boundary. It is not hidden inside `KlingVideoProvider`, and Phase 2.7D is the milestone that will connect hosted scene images to Kling image-to-video execution.
- Mock remains the default image provider. Real OpenAI image generation is opt-in only and is not invoked automatically by `GamingMediaAgent`, the integrated content pipeline, or automated tests.
- Mock remains the default TTS provider. Real OpenAI speech generation is opt-in only and is not invoked automatically by `GamingMediaAgent`, the integrated content pipeline, or automated tests.
- Dedicated real video providers such as Kling remain planned but are not implemented in this milestone.
- Kling is treated as visuals-only in CreatorOS. OpenAI TTS remains authoritative for narration, and FFmpeg composition plus captions remain unchanged.
- OpenAI SDK client objects, temporary provider URLs, and binary image payloads remain inside the adapter boundary. No image files, storage uploads, or permanent asset materialization are created in this milestone.
- OpenAI SDK client objects and binary speech payloads remain inside the adapter boundary. No narration files, storage uploads, or durable audio materialization are created in this milestone.
- Capability-specific mock registry helpers now exist for image, TTS, and video provider setup in addition to the existing full mock registry bootstrap.
- `GamingMediaAgent` remains planning-only and does not call these providers yet.
- `GamingContentPipeline` remains unchanged in responsibility and still stops at the pre-publication human-review boundary.
- Real video providers remain later milestones, and guarded live image or TTS smoke commands are still deferred.

## Video / Rendering Foundation

CreatorOS now also includes a separate provider-independent rendering foundation for final Short composition:

- `VideoProvider` remains the future contract for prompt-to-generated video clips.
- Final Short composition now uses a separate `RenderProvider` boundary so clip generation and edited-output rendering do not blur together.
- The render contracts are `RenderScene`, `ShortRenderRequest`, `RenderTransition`, and `RenderedVideo`.
- `ShortRenderRequest` validates sequential scene numbering, positive scene durations, positive dimensions and FPS, and computes deterministic total duration from scenes.
- Narration remains optional. If a narration duration estimate is present, it must not exceed total scene duration by more than one second.
- `MockRenderProvider` returns deterministic mock rendered-video references without network calls, FFmpeg, MoviePy, binary output, or local file creation.
- `MediaRenderService` can resolve the configured default render provider and execute one composition request, but it does not generate images, generate speech, upload assets, or mutate workflow state.
- `GamingMediaAgent` remains planning-only, and `GamingContentPipeline` remains pre-publication only.
- No actual MP4 rendering, caption burn-in, subtitle timing, audio mixing, transition rendering, or publishing integration exists in this milestone.

## Media Generation Services

CreatorOS now also includes an application-layer `MediaGenerationService` for provider-independent media execution:

- `GamingMediaAgent` still produces planning outputs only.
- `MediaGenerationService` is the separate application boundary that executes `ImageProvider`, `TTSProvider`, and `VideoProvider` using existing typed request contracts.
- The service supports one-off `generate_image`, `generate_audio`, and `generate_video` operations plus bounded package generation through `MediaGenerationPackageRequest`.
- `GeneratedMediaPackage` aggregates typed `GeneratedImage`, `GeneratedAudio`, and `GeneratedVideo` results without exposing raw provider payloads, SDK objects, or credentials.
- Mock remains the default runtime path, and automated tests stay fully offline.
- The same service can use real provider adapters such as `OpenAIImageProvider` and `OpenAITTSProvider` through the shared `ProviderRegistry` when explicitly registered.
- The service does not invoke `GamingMediaAgent`, `LLMExecutionService`, `MediaRenderService`, `RenderProvider`, publishing providers, storage providers, or workflow-state mutation.
- The generated media contracts may now carry an ephemeral `payload_bytes` field for local runtime materialization, but `MediaGenerationService` still does not write files itself.
- The same ephemeral `GeneratedImage.payload_bytes` mechanism is the intended future handoff for real image-to-video adapters that need source image bytes without reordering the current pipeline.
- Provider-specific task submission and polling stay inside the video adapter boundary. CreatorOS services and orchestrators still call `await provider.generate(VideoGenerationRequest)` and do not manage provider task state directly.
- Paid video task submission is never retried automatically. Polling the same task is allowed, but CreatorOS must not silently resubmit a second paid generation request.
- The next media stage will assemble a `GeneratedMediaPackage` into a `ShortRenderRequest` for rendering rather than mixing generation and rendering together.

## Artifact Materialization Foundation

CreatorOS now also includes `ArtifactMaterializationService` as the local runtime filesystem boundary between generated media contracts and later rendering work.

- `GeneratedImage`, `GeneratedAudio`, and `GeneratedVideo` can now carry provider-neutral ephemeral payload bytes when a provider has safe materializable output available.
- `OpenAIImageProvider` now decodes valid base64 image responses into ephemeral bytes without logging or serializing the payload.
- `OpenAITTSProvider` now returns ephemeral audio bytes for the same reason.
- `MockImageProvider` and `MockTTSProvider` return tiny deterministic valid payloads for offline materialization tests.
- `MockVideoProvider` remains payload-free, so video materialization fails safely until a later milestone introduces a real supported video payload path.
- `materialize_package(...)` turns a `GeneratedMediaPackage` into a deterministic local workspace and cleans up files created by the failed operation if package materialization aborts partway through.
- This is still local runtime output only. There is no durable storage provider, cloud upload, render pipeline, or publishing handoff here yet.

## Final Short Assembly

CreatorOS now also includes a provider-independent final assembly layer for Shorts:

- `ShortAssemblyService` accepts typed storyboard scene output plus a `GeneratedMediaPackage` and builds a deterministic `ShortRenderRequest`.
- Storyboard scenes align to generated scene images and scene videos strictly by index. Counts must either match the storyboard scene count exactly or remain empty.
- Asset-count mismatches fail before rendering. The service does not silently drop assets, duplicate assets, or reuse the last asset.
- `ShortAssemblyService` now also builds a provider-neutral `ProductionTimeline` before final rendering so pacing decisions are explicit platform behavior rather than renderer-specific behavior.
- Thumbnail output remains separate from the video timeline so it can be preserved for later publishing workflows without becoming an extra render scene.
- Narration, when present, is forwarded as the existing typed `GeneratedAudio` reference. The assembly layer does not regenerate audio or invent missing duration values.
- The production timeline remains authoritative. Scene pacing is deterministic, preserves approved storyboard order, and safely absorbs harmless rounding in the final scene rather than mutating approved input models.
- Narration is composition input only and does not extend or shorten the approved visual timeline. If known narration duration exceeds the allowed Short duration, assembly fails clearly before final rendering.
- Scene captions currently come only from existing typed storyboard `on_screen_text` fields and remain render instructions only.
- `MediaRenderService` remains the render boundary. `ShortAssemblyService` builds the request and delegates rendering through that existing application service.
- The default render path remains the deterministic mock renderer, which returns a typed `RenderedVideo` reference only.
- Real local MP4 rendering now exists through the FFmpeg provider path, while mock remains the default for offline development and automated tests.
- Publishing, scheduling, analytics, cloud storage, and broader operational hardening remain later milestones.

## FFmpeg Render Provider

CreatorOS now also includes `FFmpegRenderProvider` as the first real local render implementation.

- It consumes local materialized scene files from the artifact workspace rather than provider-owned transient references or network URLs.
- Static image scenes are converted into timed vertical video segments using FFmpeg scale-and-pad composition.
- Local video scenes are normalized to the requested dimensions, FPS, and duration before final composition.
- Optional narration can be muxed into the final output as a bounded audio track.
- FFmpeg now consumes the explicit provider-neutral production timeline from `ShortRenderRequest` rather than inventing scene timing internally.
- Final output is a local H.264/AAC MP4 at `artifacts/<run_id>/video/final_short.mp4`.
- Scene-level caption overlays can now be rendered as timed ASS subtitles derived from typed `RenderScene.caption` data.
- Caption text is treated as renderer input only. The renderer does not generate, rewrite, or transcribe captions.
- Caption wrapping is deterministic, UTF-8 subtitle files are generated inside the FFmpeg working directory, and subtitle temp files are cleaned after success or failure.
- Caption positioning currently supports provider-neutral `bottom`, `center`, and `top` anchors with vertical-video-safe margins.
- Local caption font selection is configurable through `CAPTION_FONT_NAME` and optional `CAPTION_FONT_FILE`.
- Narration audio is normalized to AAC at 48 kHz stereo when present.
- The production timeline remains authoritative. Shorter narration may end before the visual timeline, known narration that exceeds the approved timeline is rejected earlier during assembly, and missing narration-duration metadata does not invent a measured runtime.
- When narration is absent, the final MP4 currently has no audio stream rather than a fabricated silent track.
- `MockRenderProvider` remains the default renderer, so normal tests and local workflows stay offline and deterministic unless `ffmpeg` is explicitly registered and selected.
- FFmpeg must be installed separately or configured through `FFMPEG_PATH`.
- Timeline and pacing remain provider-independent. Premium motion providers such as Kling, Higgsfield, or later alternatives may supply scene assets in future milestones, but they do not define the final edit timeline.
- This milestone still does not add word-level timing, animated captions, background music, overlays beyond simple text, STT, GPU encoding, cloud rendering, or publishing.

### Manual Caption Smoke Path

After tests pass, a local manual caption smoke render may be performed with the already installed FFmpeg runtime.

- Use one tiny local PNG already materialized under the artifact workspace.
- Generate a tiny local test audio file with FFmpeg `sine` or `anullsrc`.
- Build a `ShortRenderRequest` with one 2-3 second image scene, one caption such as `CreatorOS caption test`, and the local narration/test-audio asset.
- Render at `1080x1920`.
- Confirm the resulting local MP4 is playable, the caption appears within safe vertical-video margins, and the audio track is present for the full video duration.

This smoke path is optional and local-only. It should not call a network service, OpenAI, text-to-speech generation, speech-to-text, or publishing infrastructure.

## Approved Media Execution

CreatorOS now also includes an explicit post-approval media-execution pipeline:

- `GamingContentPipeline` remains phase 1 only. It still stops after publication-readiness review and does not generate media automatically.
- `MediaExecutionPipeline` is a separate phase 2 entry point. The caller must pass both a completed `GamingContentPipelineResult` and explicit positive `HumanApproval`.
- Publication readiness does not equal human approval. Both gates must pass before any media-generation or render calls begin.
- The execution path is `GamingContentPipelineResult -> MediaGenerationService -> GeneratedMediaPackage -> ArtifactMaterializationService -> ShortAssemblyService -> MediaRenderService -> RenderedVideo`.
- Thumbnail planning becomes a thumbnail-generation request and remains outside the video timeline for later publishing work.
- Narration planning becomes a typed TTS request, and storyboard scenes become deterministic scene-image requests using existing approved planning data only.
- Optional scene-video requests are created only when aligned typed scene-visual and scene-motion plans are actually available.
- Scene image generation and scene video generation still happen in one bounded package pass before materialization, so true scene-image-to-video dependency wiring is not connected yet.
- Kling live execution is still explicitly gated. Create-task transport is now implemented and fully offline-tested, but CreatorOS still does not make live Kling API calls in this phase because the official query-task path, status schema, and success output field still need to be captured.
- Phase 2.7B is intended to add a dedicated real video adapter, and Phase 2.7C is intended to connect generated scene reference images to generated motion clips through a safe staged execution design.
- Default providers remain mock-first, so normal execution stays offline and deterministic unless real providers are explicitly registered and selected.
- Live non-mock media generation requires explicit confirmation before execution. API-key presence alone is not authorization.
- One validated run ID owns the complete workspace from generated media through materialized files and the final local MP4 path when FFmpeg rendering is used.
- Media can now be materialized locally and rendered into a real local MP4 through the explicit FFmpeg render provider, but mock remains the default and no storage or publishing exists in this milestone.

## Controlled Short Production CLI

CreatorOS now includes a small controlled CLI surface for end-to-end short production:

```bash
python -m creatoros run short --approve --plan
python -m creatoros run short --game Roblox --topic "funny myths" --approve --plan
python -m creatoros run short --approve
python -m creatoros run short --game Roblox --topic "funny myths" --approve
python -m creatoros run short --game Roblox --topic "funny myths" --approve --render-provider ffmpeg
python -m creatoros run short --game Roblox --topic "funny myths" --approve --image-provider openai-image --tts-provider openai-tts --confirm-live-calls
```

- `run short --plan` builds the deterministic approved package, runs full local preflight, and prints a typed execution summary without generating media, materializing files, rendering video, or making network calls.
- `run short` builds a deterministic approved package and executes the post-approval production pipeline only after the same preflight passes.
- Offline execution remains easy because mock media providers and the mock render provider are still the defaults.
- Plan output includes exact intended media-call counts, whether live media would be used, and the run workspace path before any paid execution begins.
- Live image or TTS generation is opt-in only and requires `--confirm-live-calls` on that execution command. Plan mode never counts as execution confirmation.
- FFmpeg is treated as a local render backend, not a paid live media provider.
- Preflight protects the run workspace by rejecting unsafe run IDs, unsupported output formats, missing live configuration, and an already-existing protected final output path.
- If a run fails after successful materialization, CreatorOS preserves those materialized artifacts for diagnostics, cleans renderer temporary working directories, and never reports false success. Automatic retry and resume are not part of this milestone.
- The command does not publish, schedule, upload, or run analytics.

## Single-Scene Video Smoke CLI

CreatorOS now also includes one explicit single-scene image-to-video smoke command for provider comparison work:

```bash
python -m creatoros run video-smoke --image-path assets/example.png --prompt "slow cinematic camera push-in" --duration 5 --plan
python -m creatoros run video-smoke --image-path assets/example.png --prompt "slow cinematic camera push-in" --duration 5 --hosting-provider mock --video-provider mock
python -m creatoros run video-smoke --image-path assets/example.png --prompt "smooth cinematic camera movement, natural environmental motion" --duration 5 --hosting-provider cloudinary --video-provider kling --confirm-live-calls
```

- `run video-smoke` performs one local-image-to-one-video clip path only. It does not build a full Short, generate narration, publish, or call YouTube.
- `run video-smoke --plan` validates the local image, derives the run workspace, and prints `image_input: local`, `hosting_calls: 1`, `video_generation_calls: 1`, `will_use_live_media`, and `execution_started: false` without making any network call.
- Mock mode exercises the full hosting, video-generation, materialization, and cleanup path offline by routing through the same provider-neutral services used for live execution.
- Live execution remains explicitly gated. API credentials alone are not authorization, and non-mock hosting or video providers still require `--confirm-live-calls`.
- The command materializes the resulting clip at `artifacts/<run_id>/video/clip_001.mp4`.
- Hosted reference cleanup is best-effort after execution. Cleanup failure does not erase a successful local video result.
- The command is intended for controlled Kling or future provider quality comparison only, not for full workflow automation.

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
