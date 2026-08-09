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
from creatoros.config import get_settings
from creatoros.core import ConfigurationError, ProviderAuthenticationError, ProviderNotFoundError
from creatoros.parsing import GamingCTAOutput
from creatoros.prompts import (
    PromptAssetDiscovery,
    PromptAssetManifest,
    PromptManifestLoader,
    create_builtin_prompt_registry,
)
from creatoros.providers import LLMUsage, create_provider_registry
from creatoros.services import LLMExecutionRequest, LLMExecutionResult


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
    default_render_provider: str = "mock"
    default_asset_hosting_provider: str = "mock"
    openai_api_key: str | None = "openai-secret"
    cloudinary_cloud_name: str | None = "demo-cloud"
    cloudinary_api_key: str | None = "cloudinary-key"
    cloudinary_api_secret: str | None = "cloudinary-secret"
    anthropic_api_key: str | None = "anthropic-secret"
    youtube_client_id: str | None = "youtube-client"
    youtube_client_secret: str | None = "youtube-secret"
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 3
    artifact_root: str = "C:/GamingAIFactory/artifacts"
    assets_dir: str = "C:/GamingAIFactory/assets"
    logs_dir: str = "C:/GamingAIFactory/logs"
    prompts_dir: str = "C:/GamingAIFactory/prompts"


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
                        "render_provider": request.render_provider_name or "mock",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 0,
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
                        "render_provider": request.render_provider_name,
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 0,
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
    assert "video_generation_calls: 0" in stdout
    assert "live_media_calls: 5" in stdout
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
                        "render_provider": "ffmpeg",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 0,
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
                        "render_provider": request.render_provider_name or "mock",
                        "scene_count": 3,
                        "image_generation_count": 4,
                        "tts_generation_count": 1,
                        "video_generation_count": 0,
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
