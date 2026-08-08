"""Unit tests for the CreatorOS CLI foundation."""

from __future__ import annotations

import io
import runpy
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from creatoros import __version__, cli
from creatoros.config import get_settings
from creatoros.core import ConfigurationError, ProviderNotFoundError
from creatoros.prompts import (
    PromptAssetDiscovery,
    PromptAssetManifest,
    PromptManifestLoader,
    create_builtin_prompt_registry,
)
from creatoros.providers import create_provider_registry


@dataclass
class StubSettings:
    """Simple settings stub for CLI tests."""

    app_name: str = "CreatorOS"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://user:secret@localhost:5432/creatoros_dev"
    default_llm_provider: str = "mock"
    openai_api_key: str | None = "openai-secret"
    anthropic_api_key: str | None = "anthropic-secret"
    youtube_client_id: str | None = "youtube-client"
    youtube_client_secret: str | None = "youtube-secret"
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 3
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
    for provider_type in ["analytics", "image", "llm", "publishing", "search", "storage", "trend", "video", "voice"]:
        assert f"{provider_type} | mock" in stdout


def test_providers_list_output_is_predictably_sorted(cli_module) -> None:
    """Provider list output should be sorted by provider type and name."""

    _, stdout, _ = run_cli(cli_module, ["providers", "list", "--mock"])
    lines = [line for line in stdout.splitlines() if " | " in line][1:]

    assert lines == [
        "analytics | mock | 1.0 | analytics",
        "image | mock | 1.0 | image_generation",
        "llm | mock | 1.0 | structured_generation, text_generation",
        "publishing | mock | 1.0 | publishing",
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


def test_prompts_list_shows_all_three_prompt_names(
    cli_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Builtin prompt listing should show the three research prompt names."""

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
        "gaming_discover_trends",
        "gaming_evaluate_opportunity",
        "gaming_expand_keywords",
    ]:
        assert prompt_name in stdout
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
    assert "only gaming_discover_trends is supported" in stderr


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
