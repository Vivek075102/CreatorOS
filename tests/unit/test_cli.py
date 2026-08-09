"""Unit tests for the CreatorOS CLI foundation."""

from __future__ import annotations

import io
import runpy
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from creatoros import __version__, cli
from creatoros.config import Settings, get_settings
from creatoros.core import (
    ConfigurationError,
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderResponseError,
)
from creatoros.domain import AssetType, GeneratedAsset, HostedAsset
from creatoros.orchestrator import VideoSmokeRequest, VideoSmokeResult
from creatoros.parsing import GamingCTAOutput
from creatoros.prompts import (
    PromptAssetDiscovery,
    PromptAssetManifest,
    PromptManifestLoader,
    create_builtin_prompt_registry,
)
from creatoros.providers import GeneratedVideo, LLMUsage, create_provider_registry
from creatoros.services import (
    ArtifactMaterializationService,
    GeneratedMediaPackage,
    LLMExecutionRequest,
    LLMExecutionResult,
    MediaProviderSelection,
)


@dataclass
class StubSettings:
    """Simple settings stub for CLI tests."""

    app_name: str = "CreatorOS"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://user:secret@localhost:5432/creatoros_dev"
    default_llm_provider: str = "mock"
    default_llm_model: str = "mock-model"
    default_image_provider: str = "mock"
    default_image_model: str | None = None
    default_tts_provider: str = "mock"
    default_tts_model: str | None = None
    default_video_provider: str = "mock"
    default_video_model: str | None = None
    default_render_provider: str = "mock"
    default_asset_hosting_provider: str = "mock"
    openai_api_key: str | None = "openai-secret"
    cloudinary_cloud_name: str | None = "demo-cloud"
    cloudinary_api_key: str | None = "cloudinary-key"
    cloudinary_api_secret: str | None = "cloudinary-secret"
    kling_api_key: str | None = "kling-test-key"
    kling_api_base_url: str = "https://api.kling.example"
    kling_video_timeout_seconds: float = 900.0
    kling_video_poll_interval_seconds: float = 0.01
    anthropic_api_key: str | None = "anthropic-secret"
    youtube_client_id: str | None = "youtube-client"
    youtube_client_secret: str | None = "youtube-secret"
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 3
    artifact_root: str = "C:/GamingAIFactory/artifacts"
    assets_dir: str = "C:/GamingAIFactory/assets"
    logs_dir: str = "C:/GamingAIFactory/logs"
    prompts_dir: str = "C:/GamingAIFactory/prompts"


MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
MINIMAL_MP4_BYTES = (
    b"\x00\x00\x00\x18ftypmp42"
    b"\x00\x00\x00\x00mp42isom"
)


def build_runtime_settings(tmp_path: Path) -> Settings:
    """Create one real Settings object for offline CLI smoke tests."""

    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=False,
        log_level="INFO",
        database_url="sqlite:///./database/creatoros.db",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider="mock",
        default_image_model=None,
        default_tts_provider="mock",
        default_tts_model=None,
        default_tts_voice="alloy",
        default_video_provider="mock",
        default_video_model="mock-model",
        default_render_provider="mock",
        default_asset_hosting_provider="mock",
        openai_api_key="openai-secret",
        cloudinary_cloud_name="demo-cloud",
        cloudinary_api_key="cloudinary-key",
        cloudinary_api_secret="cloudinary-secret",
        cloudinary_asset_folder="creatoros",
        kling_api_key="kling-test-key",
        kling_api_base_url="https://api.kling.example",
        kling_video_timeout_seconds=900.0,
        kling_video_poll_interval_seconds=0.01,
        openai_image_timeout_seconds=300.0,
        anthropic_api_key="anthropic-secret",
        youtube_client_id="youtube-client",
        youtube_client_secret="youtube-secret",
        provider_timeout_seconds=30.0,
        provider_max_retries=0,
        artifact_root=tmp_path / "artifacts",
        assets_dir=tmp_path / "assets",
        logs_dir=tmp_path / "logs",
        prompts_dir=tmp_path / "prompts",
    )


def create_test_image(tmp_path: Path, *, filename: str = "scene.png", payload: bytes = MINIMAL_PNG_BYTES) -> Path:
    """Create one local image file for CLI smoke tests."""

    image_path = tmp_path / filename
    image_path.write_bytes(payload)
    return image_path


def build_video_smoke_request(
    image_path: Path,
    *,
    hosting_provider: str = "mock",
    video_provider: str = "mock",
    confirm_live_media_calls: bool = False,
    prompt: str = "slow cinematic camera push-in",
    duration_seconds: float = 5.0,
    run_id: str = "video_smoke_test",
) -> VideoSmokeRequest:
    """Create one reusable single-scene smoke request for direct helper tests."""

    return VideoSmokeRequest(
        image_path=image_path,
        prompt=prompt,
        duration_seconds=duration_seconds,
        run_id=run_id,
        provider_selection=MediaProviderSelection(
            hosting_provider_name=hosting_provider,
            video_provider_name=video_provider,
        ),
        confirm_live_media_calls=confirm_live_media_calls,
    )


class VideoSmokeHostingSpy:
    """Record hosted-asset calls for single-scene smoke tests."""

    def __init__(self) -> None:
        self.host_calls = 0
        self.delete_calls = 0
        self.last_asset: GeneratedAsset | None = None
        self.hosted_assets: list[HostedAsset] = []

    async def host_asset(self, asset: GeneratedAsset, *, provider_name: str | None = None, context=None) -> HostedAsset:
        """Return one deterministic hosted asset without network access."""

        del context
        self.host_calls += 1
        self.last_asset = asset.model_copy(deep=True)
        hosted_asset = HostedAsset(
            source_asset=asset,
            public_url="https://example.invalid/creatoros/scene.png",
            provider_name=provider_name or "mock",
            provider_asset_id="creatoros/scene",
            mime_type="image/png",
        )
        self.hosted_assets.append(hosted_asset)
        return hosted_asset

    async def delete_hosted_asset(self, hosted_asset: HostedAsset, *, provider_name: str | None = None, context=None) -> bool:
        """Record one cleanup call and report success."""

        del hosted_asset, provider_name, context
        self.delete_calls += 1
        return True


class VideoSmokeFailingDeleteHostingSpy(VideoSmokeHostingSpy):
    """Simulate hosted-asset cleanup failure after a successful generation."""

    async def delete_hosted_asset(self, hosted_asset: HostedAsset, *, provider_name: str | None = None, context=None) -> bool:
        """Raise one cleanup failure without affecting the main result path."""

        del hosted_asset, provider_name, context
        self.delete_calls += 1
        raise ProviderResponseError("cleanup failed", code="provider_response_invalid")


class VideoSmokeFailingHostSpy(VideoSmokeHostingSpy):
    """Simulate a hosting failure before video generation begins."""

    async def host_asset(self, asset: GeneratedAsset, *, provider_name: str | None = None, context=None) -> HostedAsset:
        """Raise one provider-style hosting failure."""

        del asset, provider_name, context
        self.host_calls += 1
        raise ProviderResponseError("hosting failed", code="provider_response_invalid")


class VideoSmokeGenerationSpy:
    """Record generated video calls for single-scene smoke tests."""

    def __init__(self) -> None:
        self.video_calls = 0
        self.requests = []

    async def generate_video(self, request, *, provider_name: str | None = None, context=None) -> GeneratedVideo:
        """Return one deterministic video payload for materialization."""

        del context
        self.video_calls += 1
        self.requests.append(request.model_copy(deep=True))
        return GeneratedVideo(
            artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://generated/video/scene.mp4"),
            provider_name=provider_name or "mock",
            model="mock-video-model",
            mime_type="video/mp4",
            duration_seconds=request.duration_seconds,
            request_id="video-smoke-request",
            payload_bytes=MINIMAL_MP4_BYTES,
        )


class VideoSmokeFailingGenerationSpy(VideoSmokeGenerationSpy):
    """Simulate a provider-side generation failure with no retry."""

    async def generate_video(self, request, *, provider_name: str | None = None, context=None) -> GeneratedVideo:
        """Raise one provider-style generation failure."""

        del request, provider_name, context
        self.video_calls += 1
        raise ProviderResponseError("video failed", code="provider_response_invalid")


class VideoSmokeMaterializerSpy(ArtifactMaterializationService):
    """Count materialization calls while using the real file-writing implementation."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls = 0
        self.last_package: GeneratedMediaPackage | None = None

    def materialize_package(self, package: GeneratedMediaPackage, *, run_id: str):
        """Count one call and then perform real local materialization."""

        self.calls += 1
        self.last_package = package.model_copy(deep=True)
        return super().materialize_package(package, run_id=run_id)


class FakeLogger:
    """Capture CLI lifecycle logs for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        """Record an info log event."""

        self.events.append({"level": "info", "event": event, "kwargs": kwargs})

    def error(self, event: str, **kwargs: object) -> None:
        """Record an error log event."""

        self.events.append({"level": "error", "event": event, "kwargs": kwargs})

    def exception(self, event: str, **kwargs: object) -> None:
        """Record an exception log event."""

        self.events.append({"level": "error", "event": event, "kwargs": kwargs})

    def warning(self, event: str, **kwargs: object) -> None:
        """Record a warning log event."""

        self.events.append({"level": "warning", "event": event, "kwargs": kwargs})


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    """Reset shared settings and provider registries between tests."""

    get_settings.cache_clear()


@pytest.fixture
def cli_module(monkeypatch: pytest.MonkeyPatch):
    """Load the CLI module with safe test patches."""

    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    return cli


def run_cli(
    cli,
    argv: list[str],
) -> tuple[int, str, str]:
    """Execute the CLI with in-memory streams."""

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli._run_cli(argv=argv, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _capture_service_kwargs(
    captured: dict[str, object],
    kwargs: dict[str, object],
    service: object,
) -> object:
    """Record factory arguments and return the supplied fake service."""

    captured["service_kwargs"] = kwargs
    return service


def test_help_returns_success_and_displays_creatoros(cli_module) -> None:
    """Help output should succeed and mention CreatorOS."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--help"])

    assert exit_code == 0
    assert "CreatorOS" in stdout
    assert stderr == ""


def test_no_command_displays_help_and_returns_success(cli_module) -> None:
    """Running with no command should show help and succeed."""

    exit_code, stdout, stderr = run_cli(cli_module, [])

    assert exit_code == 0
    assert "CreatorOS" in stdout
    assert stderr == ""


def test_help_displays_run_command(cli_module) -> None:
    """Top-level help should include the deterministic run command."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--help"])

    assert exit_code == 0
    assert "run" in stdout
    assert stderr == ""


def test_help_displays_prompts_command(cli_module) -> None:
    """Top-level help should include prompt asset commands."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--help"])

    assert exit_code == 0
    assert "prompts" in stdout
    assert stderr == ""


def test_help_displays_parsers_command(cli_module) -> None:
    """Top-level help should include parser inspection commands."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--help"])

    assert exit_code == 0
    assert "parsers" in stdout
    assert stderr == ""


def test_help_displays_llm_command(cli_module) -> None:
    """Top-level help should include guarded LLM commands."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--help"])

    assert exit_code == 0
    assert "llm" in stdout
    assert stderr == ""


def test_version_displays_package_version(cli_module) -> None:
    """Version output should use the package version source."""

    exit_code, stdout, stderr = run_cli(cli_module, ["--version"])

    assert exit_code == 0
    assert __version__ in stdout
    assert stderr == ""


def test_config_validate_succeeds_without_connecting_to_postgresql(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuration validation should succeed with settings only."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    exit_code, stdout, stderr = run_cli(cli_module, ["config", "validate"])

    assert exit_code == 0
    assert "Configuration is valid." in stdout
    assert stderr == ""


def test_config_validate_prints_only_safe_fields(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config validation output should contain safe summary values only."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    exit_code, stdout, _ = run_cli(cli_module, ["config", "validate"])

    assert exit_code == 0
    assert "application_name: CreatorOS" in stdout
    assert "environment: development" in stdout
    assert "log_level: INFO" in stdout
    assert "default_llm_provider: mock" in stdout
    assert "secret" not in stdout


def test_config_show_never_exposes_database_username(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config show must not expose the database username."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    _, stdout, _ = run_cli(cli_module, ["config", "show"])

    assert "user" not in stdout


def test_config_show_never_exposes_database_password(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config show must not expose the database password."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    _, stdout, _ = run_cli(cli_module, ["config", "show"])

    assert "secret@" not in stdout


def test_config_show_never_exposes_api_keys_or_client_secrets(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config show must not expose API keys or client secrets."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    _, stdout, _ = run_cli(cli_module, ["config", "show"])

    assert "openai-secret" not in stdout
    assert "anthropic-secret" not in stdout
    assert "youtube-secret" not in stdout


def test_config_show_displays_safe_database_driver_host_and_name(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config show should display safe database summary fields."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    _, stdout, _ = run_cli(cli_module, ["config", "show"])

    assert "database_driver: postgresql+psycopg" in stdout
    assert "database_host: localhost" in stdout
    assert "database_name: creatoros_dev" in stdout


def test_credential_availability_is_displayed_as_booleans(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential presence should be rendered as booleans only."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    _, stdout, _ = run_cli(cli_module, ["config", "show"])

    assert "openai_configured: true" in stdout
    assert "anthropic_configured: true" in stdout
    assert "youtube_configured: true" in stdout


def test_providers_list_on_empty_registry_succeeds(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Listing providers on an empty registry should succeed."""

    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: create_provider_registry())

    exit_code, stdout, stderr = run_cli(cli_module, ["providers", "list"])

    assert exit_code == 0
    assert stdout.strip() == "No providers registered."
    assert stderr == ""


def test_providers_list_mock_displays_every_expected_provider_type(cli_module) -> None:
    """Mock provider listing should display every expected provider type."""

    exit_code, stdout, _ = run_cli(cli_module, ["providers", "list", "--mock"])

    assert exit_code == 0
    for provider_type in [
        "analytics",
        "hosting",
        "image",
        "llm",
        "publishing",
        "render",
        "search",
        "storage",
        "trend",
        "video",
        "voice",
    ]:
        assert f"{provider_type} | mock" in stdout


def test_providers_list_output_is_predictably_sorted(cli_module) -> None:
    """Provider list output should be sorted by provider type and name."""

    _, stdout, _ = run_cli(cli_module, ["providers", "list", "--mock"])
    lines = [line for line in stdout.splitlines() if " | " in line][1:]

    assert lines == [
        "analytics | mock | 1.0 | analytics",
        "hosting | mock | 1.0 | asset_hosting",
        "image | mock | 1.0 | image_generation",
        "llm | mock | 1.0 | structured_generation, text_generation",
        "publishing | mock | 1.0 | publishing",
        "render | mock | 1.0 | rendering",
        "search | mock | 1.0 | web_search",
        "storage | mock | 1.0 | storage",
        "trend | mock | 1.0 | trend_research",
        "video | mock | 1.0 | video_generation",
        "voice | mock | 1.0 | voice_generation",
    ]


def test_providers_health_mock_reports_all_providers_healthy(cli_module) -> None:
    """Mock provider health should report all providers as healthy."""

    exit_code, stdout, _ = run_cli(cli_module, ["providers", "health", "--mock"])

    assert exit_code == 0
    assert "llm/mock: healthy" in stdout
    assert "analytics/mock: healthy" in stdout


def test_providers_health_returns_exit_code_4_for_unhealthy_provider(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unhealthy providers should return resource-unavailable exit code."""

    class UnhealthyProvider:
        @property
        def info(self):
            from creatoros.providers import ProviderCapability, ProviderInfo

            return ProviderInfo(name="mock", provider_type="llm", capabilities={ProviderCapability.TEXT_GENERATION})

        async def health_check(self) -> bool:
            return False

    registry = create_provider_registry()
    registry.register(UnhealthyProvider())
    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: registry)

    exit_code, stdout, _ = run_cli(cli_module, ["providers", "health"])

    assert exit_code == 4
    assert "llm/mock: unhealthy" in stdout


def test_provider_health_exceptions_do_not_expose_arbitrary_exception_text(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider health errors should not expose raw exception text."""

    class ExplodingProvider:
        @property
        def info(self):
            from creatoros.providers import ProviderCapability, ProviderInfo

            return ProviderInfo(name="mock", provider_type="llm", capabilities={ProviderCapability.TEXT_GENERATION})

        async def health_check(self) -> bool:
            raise RuntimeError("super-secret-provider-error")

    registry = create_provider_registry()
    registry.register(ExplodingProvider())
    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: registry)

    exit_code, stdout, _ = run_cli(cli_module, ["providers", "health"])

    assert exit_code == 4
    assert "llm/mock: error" in stdout
    assert "super-secret-provider-error" not in stdout


def test_workflows_transitions_running_displays_expected_transitions(cli_module) -> None:
    """Workflow transition inspection should display running transitions."""

    exit_code, stdout, _ = run_cli(cli_module, ["workflows", "transitions", "running"])

    assert exit_code == 0
    for value in ["awaiting_approval", "cancelled", "completed", "failed", "paused"]:
        assert value in stdout


def test_workflows_transitions_completed_displays_no_allowed_transitions(cli_module) -> None:
    """Terminal workflow statuses should report no allowed transitions."""

    exit_code, stdout, _ = run_cli(cli_module, ["workflows", "transitions", "completed"])

    assert exit_code == 0
    assert stdout.strip() == "No transitions allowed."


def test_invalid_workflow_status_returns_cli_usage_exit_code_2(cli_module) -> None:
    """Invalid workflow status input should be treated as CLI usage error."""

    exit_code, _, stderr = run_cli(cli_module, ["workflows", "transitions", "not_a_status"])

    assert exit_code == 2
    assert "invalid choice" in stderr


def test_workflows_demo_state_completes_successfully(cli_module) -> None:
    """Workflow demo-state should complete successfully."""

    exit_code, stdout, _ = run_cli(cli_module, ["workflows", "demo-state"])

    assert exit_code == 0
    assert "execution_id:" in stdout


def test_workflows_demo_state_reports_completed_status(cli_module) -> None:
    """Workflow demo-state should report completed final status."""

    _, stdout, _ = run_cli(cli_module, ["workflows", "demo-state"])

    assert "final_status: completed" in stdout


def test_workflows_demo_state_does_not_call_engines_agents_providers_or_external_services(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Workflow demo-state should use only the runtime foundation."""

    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: (_ for _ in ()).throw(RuntimeError("should not be called")))

    exit_code, stdout, _ = run_cli(cli_module, ["workflows", "demo-state"])

    assert exit_code == 0
    assert "recorded_events:" in stdout


def test_run_gaming_without_approve_reports_awaiting_approval(cli_module) -> None:
    """The demo gaming run should stop at approval when not approved."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "gaming"])

    assert exit_code == 0
    assert "final_status: awaiting_approval" in stdout
    assert "published: false" in stdout
    assert "approval_request_id:" in stdout
    assert "selected_opportunity: Minecraft: Gaming Facts" in stdout
    assert stderr == ""


def test_run_gaming_with_approve_reports_completed(cli_module) -> None:
    """The approved demo gaming run should complete publishing."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "gaming", "--approve"])

    assert exit_code == 0
    assert "final_status: completed" in stdout
    assert "published: true" in stdout
    assert "published_post_id:" in stdout
    assert "published_url: mock://published/" in stdout
    assert stderr == ""


def test_run_gaming_output_does_not_expose_full_prompts_or_scripts(cli_module) -> None:
    """The CLI output should stay high-level and avoid prompt or body leakage."""

    _, stdout, _ = run_cli(cli_module, ["run", "gaming", "--approve"])

    assert "Mock generated text." not in stdout
    assert "Follow CreatorOS for more gaming shorts." not in stdout


def test_run_gaming_output_does_not_expose_secrets(cli_module) -> None:
    """The deterministic gaming command should not expose credentials."""

    _, stdout, _ = run_cli(cli_module, ["run", "gaming", "--approve"])

    assert "secret" not in stdout.casefold()
    assert "openai" not in stdout.casefold()


def test_run_gaming_invalid_platform_returns_usage_exit_code_2(cli_module) -> None:
    """Invalid platform values should be treated as CLI usage errors."""

    exit_code, _, stderr = run_cli(cli_module, ["run", "gaming", "--platform", "invalid_platform"])

    assert exit_code == 2
    assert "invalid choice" in stderr


def test_run_gaming_accepts_explicit_game_and_topic(cli_module) -> None:
    """Explicit game and topic values should be accepted by the CLI."""

    exit_code, stdout, _ = run_cli(
        cli_module,
        ["run", "gaming", "--game", "Roblox", "--topic", "funny myths", "--approve"],
    )

    assert exit_code == 0
    assert "selected_opportunity: Roblox: Funny Myths" in stdout
    assert "script_title: Roblox: Funny Myths" in stdout
    assert "Roblox" in stdout
    assert "Funny Myths" in stdout
    assert "Elden Ring" not in stdout


def test_run_help_displays_short_command(cli_module) -> None:
    """Run help should include the short-production command."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "--help"])

    assert exit_code == 0
    assert "short" in stdout
    assert stderr == ""


def test_run_short_help_documents_plan_option(cli_module) -> None:
    """Short-production help should document offline plan mode."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "short", "--help"])

    assert exit_code == 0
    assert "--plan" in stdout
    assert stderr == ""


def test_run_short_requires_explicit_approval(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Short production must require explicit approval before execution begins."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "short"])

    assert exit_code == 3
    assert stdout == ""
    assert "--approve" in stderr


def test_run_short_mock_execution_reports_summary(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline short production should print a high-level success summary."""

    from creatoros import orchestrator

    captured: dict[str, object] = {}

    class FakePipeline:
        def build_execution_plan(self, request):
            captured["planned_request"] = request
            return cast(
                object,
                type(
                    "FakePlan",
                    (),
                    {
                        "run_id": request.run_id,
                        "approved": True,
                        "image_provider": "mock",
                        "tts_provider": "mock",
                        "video_provider": "mock",
                        "hosting_provider": "mock",
                        "render_provider": request.render_provider_name or "mock",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 3,
                        "asset_hosting_calls": 3,
                        "live_media_call_count": 0,
                        "will_use_live_media": False,
                        "workspace_path": f"C:/GamingAIFactory/artifacts/{request.run_id}",
                        "output_format": request.output_format,
                        "execution_started": False,
                    },
                )(),
            )

        async def execute(self, request):
            captured["request"] = request
            return cast(
                object,
                type(
                    "FakeResult",
                    (),
                    {
                        "run_id": request.run_id,
                        "approval": type("Approval", (), {"approved_by": request.approval.approved_by})(),
                        "content_result": type(
                            "ContentResult",
                            (),
                            {"script": type("Script", (), {"title": request.content_result.script.title})()},
                        )(),
                        "provider_selection": request.provider_selection,
                        "render_provider_name": request.render_provider_name,
                        "materialized_media": type(
                            "MaterializedMedia",
                            (),
                            {
                                "workspace": type(
                                    "Workspace",
                                    (),
                                    {"workspace_path": Path(f"C:/GamingAIFactory/artifacts/{request.run_id}")},
                                )()
                            },
                        )(),
                        "assembly": type(
                            "Assembly",
                            (),
                            {
                                "scene_count": 3,
                                "total_duration_seconds": 30.0,
                                "rendered_video": type(
                                    "RenderedVideo",
                                    (),
                                    {
                                        "artifact": type(
                                            "Artifact",
                                            (),
                                            {"uri": "mock://rendered/video/demo.mp4"},
                                        )(),
                                        "metadata": {"output_format": "mp4"},
                                    },
                                )(),
                            },
                        )(),
                    },
                )(),
            )

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(orchestrator, "create_media_execution_pipeline", lambda **kwargs: FakePipeline())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "short", "--game", "Roblox", "--topic", "funny myths", "--approve"],
    )

    request = captured["request"]
    assert exit_code == 0
    assert "workflow: controlled short production" in stdout
    assert "run_id: short_roblox_funny_myths" in stdout
    assert "title: Roblox: Funny Myths" in stdout
    assert "final_video: mock://rendered/video/demo.mp4" in stdout
    assert "materialized_workspace: C:\\GamingAIFactory\\artifacts\\short_roblox_funny_myths" in stdout or "materialized_workspace: C:/GamingAIFactory/artifacts/short_roblox_funny_myths" in stdout
    assert "live_media_confirmed: false" in stdout
    assert stderr == ""
    assert request.confirm_live_media_calls is False


def test_run_short_plan_reports_counts_without_execution(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan mode should print counts and never start production execution."""

    from creatoros import orchestrator

    captured: dict[str, object] = {}

    class FakePipeline:
        def build_execution_plan(self, request):
            captured["request"] = request
            return cast(
                object,
                type(
                    "FakePlan",
                    (),
                    {
                        "run_id": request.run_id,
                        "approved": True,
                        "image_provider": request.provider_selection.image_provider_name,
                        "tts_provider": request.provider_selection.tts_provider_name,
                        "video_provider": request.provider_selection.video_provider_name,
                        "hosting_provider": request.provider_selection.hosting_provider_name,
                        "render_provider": request.render_provider_name,
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 3,
                        "asset_hosting_calls": 3,
                        "live_media_call_count": 8,
                        "will_use_live_media": True,
                        "workspace_path": f"C:/GamingAIFactory/artifacts/{request.run_id}",
                        "output_format": request.output_format,
                        "execution_started": False,
                    },
                )(),
            )

        async def execute(self, request):
            raise AssertionError("plan mode must not execute")

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(
            default_image_provider="openai-image",
            default_image_model="gpt-image-1",
            default_tts_provider="openai-tts",
            default_tts_model="gpt-4o-mini-tts",
        ),
    )
    monkeypatch.setattr(cli_module, "_build_short_provider_registry", lambda args: object())
    monkeypatch.setattr(orchestrator, "create_media_execution_pipeline", lambda **kwargs: FakePipeline())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "short",
            "--game",
            "Roblox",
            "--topic",
            "funny myths",
            "--approve",
            "--plan",
            "--image-provider",
            "openai-image",
            "--tts-provider",
            "openai-tts",
            "--render-provider",
            "ffmpeg",
        ],
    )

    request = captured["request"]
    assert exit_code == 0
    assert "mode: plan" in stdout
    assert "image_generation_calls: 4" in stdout
    assert "tts_generation_calls: 1" in stdout
    assert "video_generation_calls: 3" in stdout
    assert "asset_hosting_calls: 3" in stdout
    assert "live_media_calls: 8" in stdout
    assert "will_use_live_media: true" in stdout
    assert "execution_started: false" in stdout
    assert "workspace: C:\\GamingAIFactory\\artifacts\\short_roblox_funny_myths" in stdout or "workspace: C:/GamingAIFactory/artifacts/short_roblox_funny_myths" in stdout
    assert stderr == ""
    assert request.confirm_live_media_calls is False


def test_run_short_plan_with_live_providers_does_not_require_confirmation(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan mode should allow live-provider visibility without the execution confirmation flag."""

    from creatoros import orchestrator

    class FakePipeline:
        def build_execution_plan(self, request):
            return cast(
                object,
                type(
                    "FakePlan",
                    (),
                    {
                        "run_id": request.run_id,
                        "approved": True,
                        "image_provider": "openai-image",
                        "tts_provider": "openai-tts",
                        "video_provider": "mock",
                        "hosting_provider": "mock",
                        "render_provider": "ffmpeg",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 3,
                        "asset_hosting_calls": 3,
                        "live_media_call_count": 5,
                        "will_use_live_media": True,
                        "workspace_path": f"C:/GamingAIFactory/artifacts/{request.run_id}",
                        "output_format": request.output_format,
                        "execution_started": False,
                    },
                )(),
            )

        async def execute(self, request):
            raise AssertionError("plan mode must not execute")

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(
            default_image_provider="openai-image",
            default_image_model="gpt-image-1",
            default_tts_provider="openai-tts",
            default_tts_model="gpt-4o-mini-tts",
        ),
    )
    monkeypatch.setattr(cli_module, "_build_short_provider_registry", lambda args: object())
    monkeypatch.setattr(orchestrator, "create_media_execution_pipeline", lambda **kwargs: FakePipeline())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "short", "--approve", "--plan", "--image-provider", "openai-image", "--tts-provider", "openai-tts"],
    )

    assert exit_code == 0
    assert "mode: plan" in stdout
    assert "video_generation_calls: 3" in stdout
    assert "asset_hosting_calls: 3" in stdout
    assert stderr == ""


def test_run_short_live_media_requires_confirmation(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Live media providers should be blocked without explicit confirmation."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "short", "--approve", "--image-provider", "openai-image"],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "--confirm-live-calls" in stderr


def test_run_short_live_media_requires_api_key(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit live media still requires configured credentials."""

    from creatoros import orchestrator

    class FakePipeline:
        def build_execution_plan(self, request):
            raise AssertionError("execute path expected")

        async def execute(self, request):
            raise ConfigurationError("OPENAI_API_KEY is required for live image generation")

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings(openai_api_key=None))
    monkeypatch.setattr(cli_module, "_build_short_provider_registry", lambda args: object())
    monkeypatch.setattr(orchestrator, "create_media_execution_pipeline", lambda **kwargs: FakePipeline())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "short", "--approve", "--image-provider", "openai-image", "--confirm-live-calls"],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "OPENAI_API_KEY is required" in stderr


def test_run_short_ffmpeg_render_does_not_require_live_media_confirmation(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting FFmpeg alone should still allow offline execution."""

    from creatoros import orchestrator

    class FakePipeline:
        def build_execution_plan(self, request):
            return cast(
                object,
                type(
                    "FakePlan",
                    (),
                    {
                        "run_id": request.run_id,
                        "approved": True,
                        "image_provider": "mock",
                        "tts_provider": "mock",
                        "video_provider": "mock",
                        "hosting_provider": "mock",
                        "render_provider": request.render_provider_name or "mock",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 3,
                        "asset_hosting_calls": 3,
                        "live_media_call_count": 0,
                        "will_use_live_media": False,
                        "workspace_path": f"C:/GamingAIFactory/artifacts/{request.run_id}",
                        "output_format": request.output_format,
                        "execution_started": False,
                    },
                )(),
            )

        async def execute(self, request):
            return cast(
                object,
                type(
                    "FakeResult",
                    (),
                    {
                        "run_id": request.run_id,
                        "approval": type("Approval", (), {"approved_by": request.approval.approved_by})(),
                        "content_result": type(
                            "ContentResult",
                            (),
                            {"script": type("Script", (), {"title": request.content_result.script.title})()},
                        )(),
                        "provider_selection": request.provider_selection,
                        "render_provider_name": request.render_provider_name,
                        "materialized_media": type(
                            "MaterializedMedia",
                            (),
                            {
                                "workspace": type(
                                    "Workspace",
                                    (),
                                    {"workspace_path": Path(f"C:/GamingAIFactory/artifacts/{request.run_id}")},
                                )()
                            },
                        )(),
                        "assembly": type(
                            "Assembly",
                            (),
                            {
                                "scene_count": 3,
                                "total_duration_seconds": 30.0,
                                "rendered_video": type(
                                    "RenderedVideo",
                                    (),
                                    {
                                        "artifact": type(
                                            "Artifact",
                                            (),
                                            {"uri": f"C:/GamingAIFactory/artifacts/{request.run_id}/video/final_short.mp4"},
                                        )(),
                                        "metadata": {"output_format": "mp4"},
                                    },
                                )(),
                            },
                        )(),
                    },
                )(),
            )

    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(cli_module, "_build_short_provider_registry", lambda args: object())
    monkeypatch.setattr(orchestrator, "create_media_execution_pipeline", lambda **kwargs: FakePipeline())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "short", "--approve", "--render-provider", "ffmpeg"],
    )

    assert exit_code == 0
    assert "render_provider: ffmpeg" in stdout
    assert "success: true" in stdout
    assert stderr == ""


def test_openai_check_succeeds_without_network(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """The local OpenAI readiness check should not make a network request."""

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(openai_api_key=None, default_llm_model="mock-model"),
    )
    monkeypatch.setattr(
        cli_module,
        "register_openai_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should not be called")),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["llm", "openai-check"])

    assert exit_code == 0
    assert "provider: openai" in stdout
    assert "api_key_configured: false" in stdout
    assert "model_configured: false" in stdout
    assert "ready_for_live_smoke: false" in stdout
    assert stderr == ""


def test_openai_check_never_prints_api_key_value(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """The local readiness check must never reveal the API key value."""

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(openai_api_key="sk-test-secret", default_llm_model="gpt-5-mini"),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["llm", "openai-check"])

    assert exit_code == 0
    assert "sk-test-secret" not in stdout
    assert "sk-test-secret" not in stderr


def test_openai_smoke_refuses_without_confirmation_and_makes_zero_calls(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live smoke must require an explicit confirmation flag before any provider activity."""

    calls: list[str] = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings(default_llm_model="gpt-5-mini"))
    monkeypatch.setattr(
        cli_module,
        "register_openai_provider",
        lambda *args, **kwargs: calls.append("register"),
    )
    monkeypatch.setattr(
        cli_module,
        "create_llm_execution_service",
        lambda *args, **kwargs: calls.append("service"),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["llm", "openai-smoke", "--model", "test-model"])

    assert exit_code == 3
    assert stdout == ""
    assert "--confirm-live-call" in stderr
    assert calls == []


def test_openai_smoke_missing_api_key_prevents_live_call(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent API key should stop the smoke path before any provider call."""

    calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(openai_api_key=None, default_llm_model="gpt-5-mini"),
    )
    monkeypatch.setattr(
        cli_module,
        "register_openai_provider",
        lambda *args, **kwargs: calls.append("register"),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["llm", "openai-smoke", "--model", "test-model", "--confirm-live-call"],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "OPENAI_API_KEY is not configured" in stderr
    assert calls == []


def test_openai_smoke_rejects_mock_placeholder_model(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live smoke path must never silently substitute a real model for the mock placeholder."""

    calls: list[str] = []
    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(default_llm_model="mock-model"),
    )
    monkeypatch.setattr(
        cli_module,
        "register_openai_provider",
        lambda *args, **kwargs: calls.append("register"),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["llm", "openai-smoke", "--confirm-live-call"])

    assert exit_code == 3
    assert stdout == ""
    assert "Provide --model <valid OpenAI model>" in stderr
    assert calls == []


def test_openai_smoke_uses_llm_execution_service_and_forwards_inputs(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The smoke path should execute through LLMExecutionService with typed output and safe output rendering."""

    captured: dict[str, object] = {}

    class FakeExecutionService:
        async def execute(self, request) -> LLMExecutionResult[GamingCTAOutput]:
            captured["request"] = request
            return LLMExecutionResult[GamingCTAOutput](
                prompt_name="gaming_cta",
                prompt_version=1,
                provider_name="openai",
                model="gpt-5-mini",
                output=GamingCTAOutput(
                    cta="Tell us which Roblox myth we should test next.",
                    alternative="Follow for more Roblox myth breakdowns.",
                ),
                usage=LLMUsage(input_tokens=12, output_tokens=9, total_tokens=21),
                request_id="req_123",
                metadata={},
            )

    def fake_register_openai_provider(registry, **kwargs):
        captured["registry"] = registry
        captured["register_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(default_llm_model="gpt-5-mini"),
    )
    monkeypatch.setattr(cli_module, "register_openai_provider", fake_register_openai_provider)
    monkeypatch.setattr(
        cli_module,
        "create_llm_execution_service",
        lambda **kwargs: _capture_service_kwargs(captured, kwargs, FakeExecutionService()),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "llm",
            "openai-smoke",
            "--model",
            "gpt-5-mini",
            "--game",
            "Roblox",
            "--topic",
            "funny myths",
            "--platform",
            "youtube_shorts",
            "--tone",
            "natural",
            "--confirm-live-call",
        ],
    )

    request = cast(LLMExecutionRequest, captured["request"])
    assert exit_code == 0
    assert request.prompt_name == "gaming_cta"
    assert request.provider_name == "openai"
    assert request.model == "gpt-5-mini"
    assert request.variables == {
        "game": "Roblox",
        "topic": "funny myths",
        "platform": "youtube_shorts",
        "tone": "natural",
    }
    assert captured["register_kwargs"] == {"default_model": "gpt-5-mini"}
    assert captured["service_kwargs"]["provider_registry"] is captured["registry"]
    assert "provider_name: openai" in stdout
    assert "model: gpt-5-mini" in stdout
    assert "prompt_name: gaming_cta" in stdout
    assert "output_model: GamingCTAOutput" in stdout
    assert "request_id: req_123" in stdout
    assert "input_tokens: 12" in stdout
    assert "output_tokens: 9" in stdout
    assert "total_tokens: 21" in stdout
    assert "success: true" in stdout
    assert "CTA:" in stdout
    assert "ALTERNATIVE:" in stdout
    assert "Tell us which Roblox myth we should test next." in stdout
    assert "Follow for more Roblox myth breakdowns." in stdout
    assert "Authorization" not in stdout
    assert "system" not in stdout.casefold()
    assert "user" not in stdout.casefold()
    assert stderr == ""


def test_openai_smoke_uses_default_safe_inputs_when_not_overridden(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default smoke-test inputs should remain deterministic and compact."""

    captured: dict[str, object] = {}

    class FakeExecutionService:
        async def execute(self, request) -> LLMExecutionResult[GamingCTAOutput]:
            captured["request"] = request
            return LLMExecutionResult[GamingCTAOutput](
                prompt_name="gaming_cta",
                prompt_version=1,
                provider_name="openai",
                model="gpt-5-mini",
                output=GamingCTAOutput(cta="CTA text", alternative="Alternative text"),
                usage=None,
                request_id=None,
                metadata={},
            )

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(default_llm_model="gpt-5-mini"),
    )
    monkeypatch.setattr(cli_module, "register_openai_provider", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli_module, "create_llm_execution_service", lambda **kwargs: FakeExecutionService())

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["llm", "openai-smoke", "--model", "gpt-5-mini", "--confirm-live-call"],
    )

    request = cast(LLMExecutionRequest, captured["request"])
    assert exit_code == 0
    assert request.variables == {
        "game": "Minecraft",
        "topic": "gaming myths",
        "platform": "youtube_shorts",
        "tone": "natural",
    }
    assert "request_id: none" in stdout
    assert "input_tokens: None" in stdout
    assert "output_tokens: None" in stdout
    assert "total_tokens: None" in stdout
    assert stderr == ""


def test_openai_smoke_provider_errors_return_safe_resource_exit_code(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider failures should map to the CLI resource-unavailable exit code."""

    class ExplodingExecutionService:
        async def execute(self, request) -> LLMExecutionResult[GamingCTAOutput]:
            del request
            raise ProviderAuthenticationError("OpenAI authentication failed")

    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: StubSettings(default_llm_model="gpt-5-mini"),
    )
    monkeypatch.setattr(cli_module, "register_openai_provider", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli_module,
        "create_llm_execution_service",
        lambda **kwargs: ExplodingExecutionService(),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["llm", "openai-smoke", "--model", "gpt-5-mini", "--confirm-live-call"],
    )

    assert exit_code == 4
    assert stdout == ""
    assert "Error: OpenAI authentication failed" in stderr


def test_run_help_displays_video_smoke_command(cli_module) -> None:
    """Run help should include the single-scene video smoke command."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "--help"])

    assert exit_code == 0
    assert "video-smoke" in stdout
    assert stderr == ""


def test_run_video_smoke_help_documents_required_inputs(cli_module) -> None:
    """Video smoke help should document the local image and planning inputs."""

    exit_code, stdout, stderr = run_cli(cli_module, ["run", "video-smoke", "--help"])

    assert exit_code == 0
    assert "--image-path" in stdout
    assert "--prompt" in stdout
    assert "--plan" in stdout
    assert "--confirm-live-calls" in stdout
    assert stderr == ""


def test_run_video_smoke_missing_image_is_rejected(cli_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A missing local source image should fail before any provider work."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(tmp_path / "missing.png"),
            "--prompt",
            "slow cinematic camera push-in",
        ],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "image_path must point to an existing local file" in stderr


def test_run_video_smoke_unsupported_extension_is_rejected(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Only PNG and JPEG inputs should be accepted for the smoke command."""

    image_path = create_test_image(tmp_path, filename="scene.gif")
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "slow cinematic camera push-in",
        ],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "supported PNG or JPEG extension" in stderr


def test_run_video_smoke_blank_prompt_is_rejected(cli_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Blank motion prompts should fail at the CLI validation boundary."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["run", "video-smoke", "--image-path", str(image_path), "--prompt", "   "],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "prompt must not be blank" in stderr


def test_run_video_smoke_rejects_kling_duration_below_minimum(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Kling-selected smoke durations must respect the lower provider bound."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, _, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--duration",
            "2",
            "--video-provider",
            "kling",
        ],
    )

    assert exit_code == 3
    assert "at least 3 seconds" in stderr


def test_run_video_smoke_rejects_kling_duration_above_maximum(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Kling-selected smoke durations must respect the upper provider bound."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, _, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--duration",
            "16",
            "--video-provider",
            "kling",
        ],
    )

    assert exit_code == 3
    assert "not exceed 15 seconds" in stderr


def test_run_video_smoke_plan_never_builds_execution_services(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Plan mode should stay offline even when live providers are selected."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))
    monkeypatch.setattr(
        cli_module,
        "_create_video_smoke_services",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("plan must not build services")),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--hosting-provider",
            "cloudinary",
            "--video-provider",
            "kling",
            "--plan",
        ],
    )

    assert exit_code == 0
    assert "image_input: local" in stdout
    assert "hosting_calls: 1" in stdout
    assert "video_generation_calls: 1" in stdout
    assert "will_use_live_media: true" in stdout
    assert "execution_started: false" in stdout
    assert stderr == ""


def test_video_smoke_execution_hosts_once_generates_once_materializes_once_and_cleans_up(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The direct execution helper should use one host, one video call, and one cleanup."""

    settings = build_runtime_settings(tmp_path)
    image_path = create_test_image(tmp_path)
    request = build_video_smoke_request(image_path)
    hosting_spy = VideoSmokeHostingSpy()
    generation_spy = VideoSmokeGenerationSpy()
    materializer_spy = VideoSmokeMaterializerSpy(settings)

    monkeypatch.setattr(
        cli_module,
        "_create_video_smoke_services",
        lambda **kwargs: (
        hosting_spy,
        generation_spy,
        materializer_spy,
        ),
    )

    result = cli.asyncio.run(
        cli_module._execute_video_smoke_workflow(
            request=request,
            settings=settings,
            provider_registry=object(),
            logger=FakeLogger(),
        )
    )

    assert isinstance(result, VideoSmokeResult)
    assert hosting_spy.host_calls == 1
    assert hosting_spy.delete_calls == 1
    assert generation_spy.video_calls == 1
    assert materializer_spy.calls == 1
    assert generation_spy.requests[0].reference_image is not None
    assert generation_spy.requests[0].reference_image.uri.startswith("https://")
    assert result.final_video_path.name == "clip_001.mp4"
    assert result.final_video_path.is_file()


def test_video_smoke_cleanup_failure_does_not_fail_successful_execution(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Best-effort cleanup failures should not erase a successful local video result."""

    settings = build_runtime_settings(tmp_path)
    image_path = create_test_image(tmp_path)
    request = build_video_smoke_request(image_path, run_id="video_smoke_cleanup")
    hosting_spy = VideoSmokeFailingDeleteHostingSpy()
    generation_spy = VideoSmokeGenerationSpy()
    materializer_spy = VideoSmokeMaterializerSpy(settings)

    monkeypatch.setattr(
        cli_module,
        "_create_video_smoke_services",
        lambda **kwargs: (
        hosting_spy,
        generation_spy,
        materializer_spy,
        ),
    )

    result = cli.asyncio.run(
        cli_module._execute_video_smoke_workflow(
            request=request,
            settings=settings,
            provider_registry=object(),
            logger=FakeLogger(),
        )
    )

    assert result.run_id == "video_smoke_cleanup"
    assert hosting_spy.host_calls == 1
    assert hosting_spy.delete_calls == 1
    assert generation_spy.video_calls == 1
    assert materializer_spy.calls == 1
    assert result.final_video_path.is_file()


def test_video_smoke_hosting_failure_prevents_video_generation(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A hosting failure should stop the workflow before any video request is made."""

    settings = build_runtime_settings(tmp_path)
    image_path = create_test_image(tmp_path)
    request = build_video_smoke_request(image_path)
    hosting_spy = VideoSmokeFailingHostSpy()
    generation_spy = VideoSmokeGenerationSpy()
    materializer_spy = VideoSmokeMaterializerSpy(settings)

    monkeypatch.setattr(
        cli_module,
        "_create_video_smoke_services",
        lambda **kwargs: (
        hosting_spy,
        generation_spy,
        materializer_spy,
        ),
    )

    with pytest.raises(ProviderResponseError, match="hosting failed"):
        cli.asyncio.run(
            cli_module._execute_video_smoke_workflow(
                request=request,
                settings=settings,
                provider_registry=object(),
                logger=FakeLogger(),
            )
        )

    assert hosting_spy.host_calls == 1
    assert generation_spy.video_calls == 0
    assert materializer_spy.calls == 0


def test_video_smoke_generation_failure_propagates_without_retry(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A video-generation failure should surface cleanly after one attempted task only."""

    settings = build_runtime_settings(tmp_path)
    image_path = create_test_image(tmp_path)
    request = build_video_smoke_request(image_path)
    hosting_spy = VideoSmokeHostingSpy()
    generation_spy = VideoSmokeFailingGenerationSpy()
    materializer_spy = VideoSmokeMaterializerSpy(settings)

    monkeypatch.setattr(
        cli_module,
        "_create_video_smoke_services",
        lambda **kwargs: (
        hosting_spy,
        generation_spy,
        materializer_spy,
        ),
    )

    with pytest.raises(ProviderResponseError, match="video failed"):
        cli.asyncio.run(
            cli_module._execute_video_smoke_workflow(
                request=request,
                settings=settings,
                provider_registry=object(),
                logger=FakeLogger(),
            )
        )

    assert hosting_spy.host_calls == 1
    assert hosting_spy.delete_calls == 1
    assert generation_spy.video_calls == 1
    assert materializer_spy.calls == 0


def test_run_video_smoke_live_execution_requires_confirmation(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Live hosting or video providers must still require explicit confirmation."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))
    monkeypatch.setattr(
        cli_module,
        "_build_video_smoke_provider_registry",
        lambda args: (_ for _ in ()).throw(AssertionError("execution should not start")),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--hosting-provider",
            "cloudinary",
            "--video-provider",
            "kling",
        ],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "--confirm-live-calls" in stderr


def test_run_video_smoke_api_key_presence_alone_does_not_authorize_live_execution(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Configured credentials alone must not bypass the explicit live-call gate."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--hosting-provider",
            "cloudinary",
            "--video-provider",
            "kling",
        ],
    )

    assert exit_code == 3
    assert stdout == ""
    assert "--confirm-live-calls" in stderr


def test_run_video_smoke_live_execution_with_confirmation_is_allowed_through_policy(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit confirmation should allow the live-provider path to proceed to execution."""

    image_path = create_test_image(tmp_path)
    settings = build_runtime_settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli_module,
        "_build_video_smoke_provider_registry",
        lambda args, allowed_image_path: object(),
    )

    captured: dict[str, object] = {}

    async def fake_execute_video_smoke_workflow(*, request, settings, provider_registry, logger):
        captured["request"] = request
        captured["settings"] = settings
        captured["provider_registry"] = provider_registry
        del logger
        return VideoSmokeResult(
            run_id=request.run_id,
            provider_selection=request.provider_selection,
            duration_seconds=request.duration_seconds,
            materialized_workspace=settings.artifact_root / request.run_id,
            final_video_path=settings.artifact_root / request.run_id / "video" / "clip_001.mp4",
        )

    monkeypatch.setattr(cli_module, "_execute_video_smoke_workflow", fake_execute_video_smoke_workflow)

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "smooth motion",
            "--hosting-provider",
            "cloudinary",
            "--video-provider",
            "kling",
            "--confirm-live-calls",
        ],
    )

    request = cast(VideoSmokeRequest, captured["request"])
    assert exit_code == 0
    assert request.confirm_live_media_calls is True
    assert "workflow: video smoke" in stdout
    assert "hosting_provider: cloudinary" in stdout
    assert "video_provider: kling" in stdout
    assert "success: true" in stdout
    assert stderr == ""


def test_run_video_smoke_mock_execution_reports_summary_without_prompt_or_secret_leaks(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The mock CLI path should succeed offline and keep output high-level only."""

    image_path = create_test_image(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: build_runtime_settings(tmp_path))

    exit_code, stdout, stderr = run_cli(
        cli_module,
        [
            "run",
            "video-smoke",
            "--image-path",
            str(image_path),
            "--prompt",
            "do not print this prompt",
        ],
    )

    assert exit_code == 0
    assert "workflow: video smoke" in stdout
    assert "hosting_provider: mock" in stdout
    assert "video_provider: mock" in stdout
    assert "final_video:" in stdout
    assert "clip_001.mp4" in stdout
    assert "https://example.invalid/" not in stdout
    assert "do not print this prompt" not in stdout
    assert "cloudinary-key" not in stdout
    assert "kling-test-key" not in stdout
    assert "youtube" not in stdout.casefold()
    assert stderr == ""


def test_prompts_manifest_show_reports_schema_version_and_zero_entries(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt manifest show should report schema version and entry count."""

    _create_empty_prompt_structure(tmp_path)
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "manifest", "show"])

    assert exit_code == 0
    assert "schema_version: 1" in stdout
    assert "entries: 0" in stdout
    assert stderr == ""


def test_prompts_manifest_validate_succeeds_for_initial_empty_structure(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt manifest validation should succeed for the empty initial structure."""

    _create_empty_prompt_structure(tmp_path)
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))
    monkeypatch.setattr(cli_module, "PromptAssetDiscovery", lambda: PromptAssetDiscovery(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "manifest", "validate"])

    assert exit_code == 0
    assert "Prompt manifest is valid." in stdout
    assert "entries: 0" in stdout
    assert stderr == ""


def test_prompts_discover_reports_zero_assets_initially(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt discovery should succeed with zero assets in the initial structure."""

    _create_empty_prompt_structure(tmp_path)
    monkeypatch.setattr(cli_module, "PromptAssetDiscovery", lambda: PromptAssetDiscovery(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "discover"])

    assert exit_code == 0
    assert stdout.strip() == "Discovered prompt assets: 0"
    assert stderr == ""


def test_prompts_cli_does_not_print_prompt_contents(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt CLI commands should avoid printing prompt bodies."""

    _create_empty_prompt_structure(tmp_path)
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "manifest", "show"])

    assert exit_code == 0
    assert "You are a prompt." not in stdout
    assert "sha256" not in stdout.casefold()
    assert stderr == ""


def test_prompts_list_shows_all_seventeen_prompt_names(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Builtin prompt listing should show every current builtin prompt name."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "list"])

    assert exit_code == 0
    for prompt_name in [
        "gaming_cta",
        "gaming_discover_trends",
        "gaming_evaluate_opportunity",
        "gaming_evidence_consistency_review",
        "gaming_expand_keywords",
        "gaming_hook",
        "gaming_narration_direction",
        "gaming_publication_readiness_review",
        "gaming_scene_motion_prompt",
        "gaming_scene_visual_prompt",
        "gaming_script_quality_review",
        "gaming_storyboard_quality_review",
        "gaming_thumbnail_concept",
        "storyboard_scene_breakdown",
        "storyboard_timing_review",
        "storyboard_visual_direction",
        "youtube_shorts_script",
    ]:
        assert prompt_name in stdout
    assert stderr == ""


def test_parsers_list_succeeds_and_lists_all_seventeen_registrations(cli_module) -> None:
    """Parser listing should succeed and report all builtin registrations."""

    exit_code, stdout, stderr = run_cli(cli_module, ["parsers", "list"])
    lines = [line for line in stdout.splitlines() if " | " in line]

    assert exit_code == 0
    assert lines[0] == "prompt_name | output_model"
    assert len(lines[1:]) == 17
    assert stderr == ""


def test_parsers_list_shows_expected_output_model_names(cli_module) -> None:
    """Parser listing should show stable expected output model names."""

    exit_code, stdout, _ = run_cli(cli_module, ["parsers", "list"])

    assert exit_code == 0
    assert "gaming_discover_trends | GamingTrendDiscoveryOutput" in stdout
    assert "youtube_shorts_script | YouTubeShortsScriptOutput" in stdout
    assert "gaming_publication_readiness_review | GamingPublicationReadinessReviewOutput" in stdout


def test_parsers_list_is_deterministic(cli_module) -> None:
    """Parser list output should remain predictably ordered."""

    _, stdout, _ = run_cli(cli_module, ["parsers", "list"])
    lines = [line for line in stdout.splitlines() if " | " in line][1:]

    assert lines == sorted(lines)


def test_parsers_list_does_not_call_providers(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Parser listing should not resolve provider registries."""

    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: (_ for _ in ()).throw(RuntimeError("should not be called")))

    exit_code, stdout, stderr = run_cli(cli_module, ["parsers", "list"])

    assert exit_code == 0
    assert "prompt_name | output_model" in stdout
    assert stderr == ""


def test_parsers_validate_succeeds_and_reports_valid_contract(cli_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Parser validation should succeed for the current builtin prompt/parser contract."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["parsers", "validate"])

    assert exit_code == 0
    assert "valid: true" in stdout
    assert "prompt_count: 17" in stdout
    assert "parser_count: 17" in stdout
    assert "missing_parsers: (none)" in stdout
    assert "orphan_parsers: (none)" in stdout
    assert stderr == ""


def test_parsers_validate_does_not_call_providers(cli_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Parser validation should not resolve provider registries."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )
    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: (_ for _ in ()).throw(RuntimeError("should not be called")))

    exit_code, stdout, stderr = run_cli(cli_module, ["parsers", "validate"])

    assert exit_code == 0
    assert "valid: true" in stdout
    assert stderr == ""


def test_prompts_list_does_not_print_prompt_contents(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt listing should stay high-level and avoid body output."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, stdout, _ = run_cli(cli_module, ["prompts", "list"])

    assert exit_code == 0
    assert "You are a gaming content research analyst." not in stdout
    assert "OUTPUT FORMAT" not in stdout


def test_prompts_render_gaming_discover_trends_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_discover_trends."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "render", "gaming_discover_trends"])

    assert exit_code == 0
    assert "prompt_name: gaming_discover_trends" in stdout
    assert "prompt_version: 1" in stdout
    assert "message_count:" in stdout
    assert "variable_names:" in stdout
    assert stderr == ""


def test_prompts_render_youtube_shorts_script_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for youtube_shorts_script."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "render", "youtube_shorts_script"])

    assert exit_code == 0
    assert "prompt_name: youtube_shorts_script" in stdout
    assert "prompt_version: 1" in stdout
    assert "message_count:" in stdout
    assert "variable_names:" in stdout
    assert stderr == ""


def test_default_render_does_not_print_full_content(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default local rendering should avoid printing full prompt content."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(cli_module, ["prompts", "render", "gaming_discover_trends"])

    assert exit_code == 0
    assert "Rendered locally only." not in stdout
    assert "RESEARCH_SIGNALS:" not in stdout
    assert "WHY_NOW:" not in stdout


def test_show_content_prints_rendered_content(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit content display should print rendered prompt text."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        ["prompts", "render", "gaming_discover_trends", "--show-content"],
    )

    assert exit_code == 0
    assert "Rendered locally only. No provider call occurred." in stdout
    assert "RESEARCH_SIGNALS:" in stdout
    assert "WHY_NOW:" in stdout


def test_show_content_prints_full_youtube_shorts_script_rendered_content(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit content display should print rendered short-form script prompt text."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        ["prompts", "render", "youtube_shorts_script", "--show-content"],
    )

    assert exit_code == 0
    assert "Rendered locally only. No provider call occurred." in stdout
    assert "HOOK_DIRECTION:" in stdout
    assert "CALL_TO_ACTION:" in stdout
    assert "EVIDENCE_NOTE:" in stdout


def test_custom_game_and_topic_values_are_reflected_when_content_is_shown(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Shown prompt content should reflect custom render inputs."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        [
            "prompts",
            "render",
            "gaming_discover_trends",
            "--game",
            "Roblox",
            "--topic",
            "funny myths",
            "--signals",
            "Players are discussing recurring myths about game mechanics.",
            "--show-content",
        ],
    )

    assert exit_code == 0
    assert "GAME: Roblox" in stdout
    assert "TOPIC: funny myths" in stdout
    assert "Players are discussing recurring myths about game mechanics." in stdout


def test_custom_script_prompt_values_are_reflected_when_content_is_shown(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Shown script prompt content should reflect custom render inputs."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        [
            "prompts",
            "render",
            "youtube_shorts_script",
            "--title",
            "Roblox: Funny Myths",
            "--game",
            "Roblox",
            "--topic",
            "funny myths",
            "--angle",
            "test three popular myths",
            "--hook-direction",
            "challenge a common belief",
            "--source-summary",
            "Supplied research notes discuss recurring myths about game mechanics.",
            "--show-content",
        ],
    )

    assert exit_code == 0
    assert "TITLE: Roblox: Funny Myths" in stdout
    assert "GAME: Roblox" in stdout
    assert "TOPIC: funny myths" in stdout
    assert "ANGLE: test three popular myths" in stdout
    assert "HOOK_DIRECTION: challenge a common belief" in stdout
    assert "SOURCE_SUMMARY: Supplied research notes discuss recurring myths about game mechanics." in stdout


def test_prompts_render_gaming_hook_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_hook."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_hook", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_hook" in stdout
    assert "HOOK_1:" in stdout
    assert "BEST_HOOK:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_cta_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_cta."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_cta", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_cta" in stdout
    assert "CTA:" in stdout
    assert "ALTERNATIVE:" in stdout
    assert stderr == ""


def test_prompts_render_storyboard_scene_breakdown_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for storyboard_scene_breakdown."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "storyboard_scene_breakdown"],
    )

    assert exit_code == 0
    assert "prompt_name: storyboard_scene_breakdown" in stdout
    assert "prompt_version: 1" in stdout
    assert stderr == ""


def test_prompts_render_storyboard_visual_direction_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for storyboard_visual_direction."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "storyboard_visual_direction", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: storyboard_visual_direction" in stdout
    assert "SCENE_NUMBER:" in stdout
    assert "AVOID:" in stdout
    assert stderr == ""


def test_prompts_render_storyboard_timing_review_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for storyboard_timing_review."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "storyboard_timing_review", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: storyboard_timing_review" in stdout
    assert "DECISION:" in stdout
    assert "RECOMMENDATIONS:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_thumbnail_concept_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_thumbnail_concept."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_thumbnail_concept", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_thumbnail_concept" in stdout
    assert "CONCEPT:" in stdout
    assert "STYLE_DIRECTION:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_scene_visual_prompt_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_scene_visual_prompt."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_scene_visual_prompt", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_scene_visual_prompt" in stdout
    assert "SCENE_NUMBER:" in stdout
    assert "NEGATIVE_GUIDANCE:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_scene_motion_prompt_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_scene_motion_prompt."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_scene_motion_prompt", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_scene_motion_prompt" in stdout
    assert "PRIMARY_MOTION:" in stdout
    assert "DURATION_SECONDS:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_narration_direction_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_narration_direction."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_narration_direction", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_narration_direction" in stdout
    assert "NARRATION_TEXT:" in stdout
    assert "PRONUNCIATION_NOTES:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_script_quality_review_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_script_quality_review."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_script_quality_review", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_script_quality_review" in stdout
    assert "HOOK_REVIEW:" in stdout
    assert "FACTUAL_RESTRAINT:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_evidence_consistency_review_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_evidence_consistency_review."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_evidence_consistency_review", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_evidence_consistency_review" in stdout
    assert "SUPPORTED_CLAIMS:" in stdout
    assert "UNSUPPORTED_CLAIMS:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_storyboard_quality_review_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_storyboard_quality_review."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_storyboard_quality_review", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_storyboard_quality_review" in stdout
    assert "SCRIPT_FIDELITY:" in stdout
    assert "UNSUPPORTED_VISUALS:" in stdout
    assert stderr == ""


def test_prompts_render_gaming_publication_readiness_review_succeeds(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local prompt rendering should succeed for gaming_publication_readiness_review."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, stderr = run_cli(
        cli_module,
        ["prompts", "render", "gaming_publication_readiness_review", "--show-content"],
    )

    assert exit_code == 0
    assert "prompt_name: gaming_publication_readiness_review" in stdout
    assert "BLOCKERS:" in stdout
    assert "HUMAN_REVIEW_FOCUS:" in stdout
    assert stderr == ""


def test_review_prompt_values_are_reflected_when_content_is_shown(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Shown review prompt content should reflect custom render inputs."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        [
            "prompts",
            "render",
            "gaming_script_quality_review",
            "--title",
            "Roblox: Funny Myths",
            "--game",
            "Roblox",
            "--topic",
            "funny myths",
            "--angle",
            "test three popular myths",
            "--source-summary",
            "Supplied research notes discuss recurring myths about Roblox game mechanics.",
            "--script-text",
            "You probably still believe this Roblox myth, so let's check the claim carefully.",
            "--duration",
            "45",
            "--show-content",
        ],
    )

    assert exit_code == 0
    assert "TITLE: Roblox: Funny Myths" in stdout
    assert "GAME: Roblox" in stdout
    assert "TOPIC: funny myths" in stdout
    assert "TARGET_DURATION_SECONDS: 45" in stdout


def test_evidence_review_prompt_values_are_reflected_when_content_is_shown(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Shown evidence-review prompt content should reflect custom render inputs."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, stdout, _ = run_cli(
        cli_module,
        [
            "prompts",
            "render",
            "gaming_evidence_consistency_review",
            "--game",
            "Roblox",
            "--source-summary",
            "Supplied summary covers one recurring gameplay myth.",
            "--research-notes",
            "Research notes say the myth should be described cautiously.",
            "--content-text",
            "This myth is definitely true in every case.",
            "--content-stage",
            "script_draft",
            "--show-content",
        ],
    )

    assert exit_code == 0
    assert "GAME: Roblox" in stdout
    assert "CONTENT_STAGE: script_draft" in stdout
    assert "CONTENT_TEXT: This myth is definitely true in every case." in stdout


def test_render_command_does_not_call_providers(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt rendering should not resolve or call providers."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )
    monkeypatch.setattr(cli_module, "get_provider_registry", lambda: (_ for _ in ()).throw(RuntimeError("should not be called")))

    exit_code, stdout, _ = run_cli(cli_module, ["prompts", "render", "gaming_discover_trends"])

    assert exit_code == 0
    assert "prompt_name: gaming_discover_trends" in stdout


def test_invalid_prompt_name_returns_safe_non_zero_exit_code(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unsupported prompt names should fail safely."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )

    exit_code, _, stderr = run_cli(cli_module, ["prompts", "render", "unknown_prompt"])

    assert exit_code == 3
    assert "the requested builtin prompt is not supported" in stderr


def test_prompt_cli_does_not_expose_secrets(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt commands should not expose secrets through normal output."""

    _copy_repo_prompt_structure(tmp_path)
    monkeypatch.setattr(
        cli_module,
        "create_builtin_prompt_registry",
        lambda: create_builtin_prompt_registry(base_dir=tmp_path),
    )
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, stdout, stderr = run_cli(cli_module, ["prompts", "list"])

    assert exit_code == 0
    combined = f"{stdout}\n{stderr}".casefold()
    assert "openai-secret" not in combined
    assert "anthropic-secret" not in combined
    assert "youtube-secret" not in combined


def test_missing_manifest_maps_to_safe_non_zero_exit_code(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing prompt manifests should return a safe resource-unavailable exit code."""

    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, _, stderr = run_cli(cli_module, ["prompts", "manifest", "show"])

    assert exit_code == 4
    assert "Error: prompt manifest file was not found" in stderr


def test_invalid_manifest_does_not_expose_file_contents(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid prompt manifest content should not expose file contents through the CLI."""

    (tmp_path / "manifest.json").write_text(
        '{"schema_version": 2, "entries": [], "metadata": {"description": "SECRET MANIFEST"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_module, "PromptManifestLoader", lambda: PromptManifestLoader(base_dir=tmp_path))

    exit_code, _, stderr = run_cli(cli_module, ["prompts", "manifest", "show"])

    assert exit_code == 3
    assert "SECRET MANIFEST" not in stderr


def test_expected_configuration_errors_return_exit_code_3(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuration errors should map to exit code 3."""

    monkeypatch.setattr(cli_module, "get_settings", lambda: (_ for _ in ()).throw(ConfigurationError("bad config")))

    exit_code, _, stderr = run_cli(cli_module, ["config", "validate"])

    assert exit_code == 3
    assert "Error: bad config" in stderr


def test_provider_not_found_errors_return_exit_code_4(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider-not-found errors should map to exit code 4."""

    monkeypatch.setattr(
        cli_module,
        "_handle_providers_list",
        lambda args, stdout, stderr: (_ for _ in ()).throw(ProviderNotFoundError("llm", "missing")),
    )

    exit_code, _, stderr = run_cli(cli_module, ["providers", "list"])

    assert exit_code == 4
    assert "Error: Provider 'missing' was not found for type 'llm'" in stderr


def test_unexpected_errors_return_exit_code_1(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected errors should map to exit code 1."""

    monkeypatch.setattr(
        cli_module,
        "_handle_config_validate",
        lambda args, stdout, stderr: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code, _, _ = run_cli(cli_module, ["config", "validate"])

    assert exit_code == 1


def test_unexpected_error_output_is_safe(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected error output should not expose raw exception text."""

    monkeypatch.setattr(
        cli_module,
        "_handle_config_validate",
        lambda args, stdout, stderr: (_ for _ in ()).throw(RuntimeError("super-secret-boom")),
    )

    exit_code, _, stderr = run_cli(cli_module, ["config", "validate"])

    assert exit_code == 1
    assert "Error: An unexpected application failure occurred." in stderr
    assert "super-secret-boom" not in stderr


def test_cli_lifecycle_logs_do_not_contain_secrets(cli_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI lifecycle logs should contain only safe metadata."""

    logger = FakeLogger()
    monkeypatch.setattr(cli_module, "get_logger", lambda name=None: logger)
    monkeypatch.setattr(cli_module, "get_settings", lambda: StubSettings())

    exit_code, _, _ = run_cli(cli_module, ["config", "show"])

    assert exit_code == 0
    combined = "".join(str(event["kwargs"]) for event in logger.events)
    assert "openai-secret" not in combined
    assert "anthropic-secret" not in combined
    assert "youtube-secret" not in combined
    assert "secret@" not in combined


def test_main_accepts_explicit_argv_list(cli_module) -> None:
    """The public main function should accept an explicit argv list."""

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = cli_module._run_cli(argv=["--version"], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert __version__ in stdout.getvalue()


def test___main___uses_the_cli_main_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """The package module entry point should delegate to creatoros.cli.main."""

    monkeypatch.setattr("creatoros.cli.main", lambda argv=None: 7)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("creatoros.__main__", run_name="__main__")

    assert exc_info.value.code == 7


def test_pyproject_contains_console_entry_point_if_required() -> None:
    """The project configuration should define the creatoros console entry point."""

    with open("pyproject.toml", encoding="utf-8") as file:
        contents = file.read()

    assert 'creatoros = "creatoros.cli:main"' in contents


def _create_empty_prompt_structure(base_dir: Path) -> None:
    """Create the initial prompt directory structure for CLI tests."""

    for category in [
        "research",
        "script",
        "storyboard",
        "narration",
        "thumbnail",
        "metadata",
        "review",
        "publishing",
    ]:
        (base_dir / category).mkdir(parents=True, exist_ok=True)
        (base_dir / category / ".gitkeep").write_text("", encoding="utf-8")
    (base_dir / "research" / "gaming").mkdir(parents=True, exist_ok=True)
    (base_dir / "research" / "common").mkdir(parents=True, exist_ok=True)
    (base_dir / "research" / "gaming" / ".gitkeep").write_text("", encoding="utf-8")
    (base_dir / "research" / "common" / ".gitkeep").write_text("", encoding="utf-8")

    PromptManifestLoader(base_dir=base_dir).write(
        PromptAssetManifest(
            metadata={"description": "CreatorOS version-controlled prompt asset manifest."}
        )
    )


def _copy_repo_prompt_structure(base_dir: Path) -> None:
    """Copy the repository prompt structure into a temporary test directory."""

    repo_prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    shutil.copytree(repo_prompts_dir, base_dir, dirs_exist_ok=True)
