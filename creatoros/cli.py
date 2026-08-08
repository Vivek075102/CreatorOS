"""Command-line interface foundation for CreatorOS."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import TextIO
from urllib.parse import urlsplit

from pydantic import ValidationError

from creatoros import __version__
from creatoros.config import get_settings
from creatoros.core import (
    ConfigurationError,
    CreatorOSError,
    CreatorOSValidationError,
    PromptLoadError,
    PromptManifestError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from creatoros.domain import ContentPlatform
from creatoros.observability import configure_logging, get_logger
from creatoros.orchestrator import GamingWorkflowInput, run_demo_gaming_workflow
from creatoros.parsing import (
    build_builtin_parser_registry,
    validate_builtin_prompt_parser_contracts,
)
from creatoros.prompts import (
    GAMING_CTA,
    GAMING_DISCOVER_TRENDS,
    GAMING_EVIDENCE_CONSISTENCY_REVIEW,
    GAMING_HOOK,
    GAMING_NARRATION_DIRECTION,
    GAMING_PUBLICATION_READINESS_REVIEW,
    GAMING_SCENE_MOTION_PROMPT,
    GAMING_SCENE_VISUAL_PROMPT,
    GAMING_SCRIPT_QUALITY_REVIEW,
    GAMING_STORYBOARD_QUALITY_REVIEW,
    GAMING_THUMBNAIL_CONCEPT,
    STORYBOARD_SCENE_BREAKDOWN,
    STORYBOARD_TIMING_REVIEW,
    STORYBOARD_VISUAL_DIRECTION,
    YOUTUBE_SHORTS_SCRIPT,
    PromptAssetDiscovery,
    PromptManifestLoader,
    create_builtin_prompt_registry,
    render_gaming_cta,
    render_gaming_discover_trends,
    render_gaming_evidence_consistency_review,
    render_gaming_hook,
    render_gaming_narration_direction,
    render_gaming_publication_readiness_review,
    render_gaming_scene_motion_prompt,
    render_gaming_scene_visual_prompt,
    render_gaming_script_quality_review,
    render_gaming_storyboard_quality_review,
    render_gaming_thumbnail_concept,
    render_storyboard_scene_breakdown,
    render_storyboard_timing_review,
    render_storyboard_visual_direction,
    render_youtube_shorts_script,
)
from creatoros.providers import get_provider_registry
from creatoros.providers.mock import create_mock_provider_registry
from creatoros.workflows import (
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowRuntime,
    get_allowed_transitions,
)

EXIT_SUCCESS = 0
EXIT_UNEXPECTED_FAILURE = 1
EXIT_USAGE_ERROR = 2
EXIT_CONFIGURATION_ERROR = 3
EXIT_RESOURCE_UNAVAILABLE = 4


class _FallbackLogger:
    """Minimal no-op logger used when structured logging cannot be configured."""

    def info(self, event: str, **kwargs: object) -> None:
        """Ignore info log calls when structured logging is unavailable."""

        del event, kwargs

    def error(self, event: str, **kwargs: object) -> None:
        """Ignore error log calls when structured logging is unavailable."""

        del event, kwargs

    def exception(self, event: str, **kwargs: object) -> None:
        """Ignore exception log calls when structured logging is unavailable."""

        del event, kwargs


@dataclass(slots=True)
class DatabaseSummary:
    """Safe database summary fields extracted from a database URL."""

    driver: str = "unknown"
    host: str = "unknown"
    name: str = "unknown"


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, execute the requested command, and return an exit code."""

    return _run_cli(argv=argv, stdout=sys.stdout, stderr=sys.stderr)


def _run_cli(
    *,
    argv: list[str] | None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Execute the CLI using explicit output streams."""

    parser = _build_parser()

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = parser.parse_args(argv)
    except SystemExit as error:
        return _normalize_system_exit_code(error.code)

    if args.command_group is None:
        _write_output(stdout, parser.format_help().rstrip())
        return EXIT_SUCCESS

    logger: object
    try:
        configure_logging()
        if args.debug:
            logging.getLogger("creatoros").setLevel(logging.DEBUG)
        logger = get_logger("cli")
    except (ConfigurationError, CreatorOSValidationError, ValidationError):
        logger = _FallbackLogger()
        if args.command_group == "config":
            pass

    logger.info(
        "cli_command_started",
        command_group=args.command_group,
        command_name=args.command_name,
    )

    try:
        exit_code = args.handler(args, stdout=stdout, stderr=stderr)
        logger.info(
            "cli_command_completed",
            command_group=args.command_group,
            command_name=args.command_name,
            exit_code=exit_code,
        )
        return exit_code
    except (ProviderNotFoundError, ProviderUnavailableError) as error:
        logger.error(
            "cli_command_failed",
            command_group=args.command_group,
            command_name=args.command_name,
            exit_code=EXIT_RESOURCE_UNAVAILABLE,
            error_type=type(error).__name__,
            error_code=error.code,
        )
        _write_error(stderr, f"Error: {error}")
        return EXIT_RESOURCE_UNAVAILABLE
    except (PromptLoadError, PromptManifestError) as error:
        exit_code = _classify_prompt_error_exit_code(error)
        logger.error(
            "cli_command_failed",
            command_group=args.command_group,
            command_name=args.command_name,
            exit_code=exit_code,
            error_type=type(error).__name__,
            error_code=error.code,
        )
        _write_error(stderr, f"Error: {error}")
        return exit_code
    except (ConfigurationError, CreatorOSValidationError, ValidationError) as error:
        logger.error(
            "cli_command_failed",
            command_group=args.command_group,
            command_name=args.command_name,
            exit_code=EXIT_CONFIGURATION_ERROR,
            error_type=type(error).__name__,
            error_code=getattr(error, "code", None),
        )
        if isinstance(error, ValidationError):
            _write_error(stderr, "Error: Configuration is invalid.")
        else:
            _write_error(stderr, f"Error: {error}")
        return EXIT_CONFIGURATION_ERROR
    except CreatorOSError as error:
        logger.error(
            "cli_command_failed",
            command_group=args.command_group,
            command_name=args.command_name,
            exit_code=EXIT_UNEXPECTED_FAILURE,
            error_type=type(error).__name__,
            error_code=error.code,
        )
        _write_error(stderr, f"Error: {error}")
        return EXIT_UNEXPECTED_FAILURE
    except Exception:
        if args.debug:
            logger.exception(
                "cli_command_failed",
                command_group=args.command_group,
                command_name=args.command_name,
                exit_code=EXIT_UNEXPECTED_FAILURE,
                error_type="unexpected_exception",
                error_code=None,
            )
        else:
            logger.error(
                "cli_command_failed",
                command_group=args.command_group,
                command_name=args.command_name,
                exit_code=EXIT_UNEXPECTED_FAILURE,
                error_type="unexpected_exception",
                error_code=None,
            )
        _write_error(stderr, "Error: An unexpected application failure occurred.")
        return EXIT_UNEXPECTED_FAILURE


def _build_parser() -> argparse.ArgumentParser:
    """Create the top-level argparse parser and its command tree."""

    parser = argparse.ArgumentParser(
        prog="creatoros",
        description="CreatorOS command-line interface.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging for this invocation.")
    parser.add_argument("--version", action="version", version=f"CreatorOS {__version__}")
    parser.set_defaults(command_group=None, command_name=None, handler=None)

    subparsers = parser.add_subparsers(dest="command_group")

    config_parser = subparsers.add_parser("config", help="Inspect and validate configuration.")
    config_subparsers = config_parser.add_subparsers(dest="command_name")

    config_validate = config_subparsers.add_parser("validate", help="Validate the current configuration.")
    config_validate.set_defaults(
        command_group="config",
        command_name="validate",
        handler=_handle_config_validate,
    )

    config_show = config_subparsers.add_parser("show", help="Show a safe configuration summary.")
    config_show.set_defaults(
        command_group="config",
        command_name="show",
        handler=_handle_config_show,
    )

    providers_parser = subparsers.add_parser("providers", help="Inspect registered providers.")
    providers_subparsers = providers_parser.add_subparsers(dest="command_name")

    providers_list = providers_subparsers.add_parser("list", help="List registered providers.")
    providers_list.add_argument("--mock", action="store_true", help="Use a fresh mock provider registry.")
    providers_list.set_defaults(
        command_group="providers",
        command_name="list",
        handler=_handle_providers_list,
    )

    providers_health = providers_subparsers.add_parser("health", help="Run provider health checks.")
    providers_health.add_argument("--mock", action="store_true", help="Use a fresh mock provider registry.")
    providers_health.set_defaults(
        command_group="providers",
        command_name="health",
        handler=_handle_providers_health,
    )

    workflows_parser = subparsers.add_parser("workflows", help="Inspect workflow foundations.")
    workflows_subparsers = workflows_parser.add_subparsers(dest="command_name")

    workflows_transitions = workflows_subparsers.add_parser(
        "transitions",
        help="Show allowed transitions for a workflow execution status.",
    )
    workflows_transitions.add_argument(
        "status",
        choices=sorted(status.value for status in WorkflowExecutionStatus),
        help="Workflow execution status to inspect.",
    )
    workflows_transitions.set_defaults(
        command_group="workflows",
        command_name="transitions",
        handler=_handle_workflow_transitions,
    )

    workflows_demo = workflows_subparsers.add_parser(
        "demo-state",
        help="Demonstrate workflow state management only.",
    )
    workflows_demo.set_defaults(
        command_group="workflows",
        command_name="demo-state",
        handler=_handle_workflow_demo_state,
    )

    prompts_parser = subparsers.add_parser("prompts", help="Inspect prompt assets and the prompt manifest.")
    prompts_subparsers = prompts_parser.add_subparsers(dest="command_name")

    prompts_manifest = prompts_subparsers.add_parser("manifest", help="Inspect the prompt asset manifest.")
    prompts_manifest_subparsers = prompts_manifest.add_subparsers(dest="prompt_manifest_command")

    prompts_manifest_show = prompts_manifest_subparsers.add_parser("show", help="Show the prompt asset manifest.")
    prompts_manifest_show.set_defaults(
        command_group="prompts",
        command_name="manifest_show",
        handler=_handle_prompts_manifest_show,
    )

    prompts_manifest_validate = prompts_manifest_subparsers.add_parser(
        "validate",
        help="Validate the prompt asset manifest against discovered assets.",
    )
    prompts_manifest_validate.set_defaults(
        command_group="prompts",
        command_name="manifest_validate",
        handler=_handle_prompts_manifest_validate,
    )

    prompts_discover = prompts_subparsers.add_parser("discover", help="Discover prompt assets on disk.")
    prompts_discover.set_defaults(
        command_group="prompts",
        command_name="discover",
        handler=_handle_prompts_discover,
    )

    prompts_list = prompts_subparsers.add_parser("list", help="List builtin prompt definitions.")
    prompts_list.set_defaults(
        command_group="prompts",
        command_name="list",
        handler=_handle_prompts_list,
    )

    prompts_render = prompts_subparsers.add_parser("render", help="Render a builtin prompt locally.")
    prompts_render.add_argument("prompt_name", help="Stable logical prompt name to render.")
    prompts_render.add_argument("--title", default="Minecraft: Gaming Facts", help="Title input for supported script and hook prompts.")
    prompts_render.add_argument("--game", default="Minecraft", help="Game input for the render helper.")
    prompts_render.add_argument("--topic", default="gaming facts", help="Topic input for the render helper.")
    prompts_render.add_argument(
        "--angle",
        default="Explain one clear gaming fact with cautious evidence.",
        help="Angle input for supported script and hook prompts.",
    )
    prompts_render.add_argument(
        "--hook-direction",
        default="Challenge a common assumption quickly",
        help="Hook direction input for the short-form script prompt.",
    )
    prompts_render.add_argument(
        "--hook",
        default="You probably missed this gaming detail.",
        help="Hook input for the storyboard scene breakdown prompt.",
    )
    prompts_render.add_argument(
        "--body",
        default="Explain one clear gaming point with concise evidence and progression.",
        help="Body input for the storyboard scene breakdown prompt.",
    )
    prompts_render.add_argument(
        "--ending",
        default="That is the quick breakdown.",
        help="Ending input for the storyboard scene breakdown prompt.",
    )
    prompts_render.add_argument(
        "--call-to-action",
        default="What should we test next?",
        help="Call to action input for the storyboard scene breakdown prompt.",
    )
    prompts_render.add_argument(
        "--signals",
        default="No live research supplied; deterministic local demonstration signal.",
        help="Supplied research signals for the render helper.",
    )
    prompts_render.add_argument(
        "--source-summary",
        default="Supplied evidence summary for local prompt rendering only.",
        help="Source summary input for supported script and hook prompts.",
    )
    prompts_render.add_argument(
        "--research-notes",
        default="Supplied research notes for local consistency review only.",
        help="Research notes input for the evidence consistency review prompt.",
    )
    prompts_render.add_argument(
        "--content-text",
        default="Generated content text under review for local consistency checking only.",
        help="Content text input for the evidence consistency review prompt.",
    )
    prompts_render.add_argument(
        "--content-stage",
        default="script_draft",
        help="Content stage input for the evidence consistency review prompt.",
    )
    prompts_render.add_argument(
        "--tone",
        default="natural and concise",
        help="Tone input for the CTA prompt.",
    )
    prompts_render.add_argument(
        "--scene-number",
        default=2,
        type=int,
        help="Scene number input for the storyboard visual direction prompt.",
    )
    prompts_render.add_argument(
        "--scene-purpose",
        default="Develop the main idea clearly",
        help="Scene purpose input for the storyboard visual direction prompt.",
    )
    prompts_render.add_argument(
        "--script-beat",
        default="Explain the main myth or fact concisely",
        help="Script beat input for the storyboard visual direction prompt.",
    )
    prompts_render.add_argument(
        "--visual-summary",
        default="Gameplay footage with concise supporting overlays",
        help="Visual summary input for the storyboard visual direction prompt.",
    )
    prompts_render.add_argument(
        "--scene-summary",
        default="Scene 1: 5 seconds hook. Scene 2: 12 seconds explanation. Scene 3: 8 seconds example. Scene 4: 5 seconds ending.",
        help="Scene timing summary input for the storyboard timing review prompt.",
    )
    prompts_render.add_argument(
        "--storyboard-text",
        default="Scene 1 supports the hook. Scene 2 explains the main point. Scene 3 reinforces the conclusion.",
        help="Storyboard text input for the storyboard quality review prompt.",
    )
    prompts_render.add_argument(
        "--storyboard-summary",
        default="Storyboard summary for local publication-readiness review only.",
        help="Storyboard summary input for the publication readiness review prompt.",
    )
    prompts_render.add_argument(
        "--visual-context",
        default="Clean gameplay-inspired context with one clear focal subject.",
        help="Visual context input for the thumbnail concept prompt.",
    )
    prompts_render.add_argument(
        "--visual-direction",
        default="Focus on one clear gameplay-related visual moment with readable overlays.",
        help="Visual direction input for the scene visual prompt.",
    )
    prompts_render.add_argument(
        "--on-screen-text",
        default="Myth or Fact?",
        help="On-screen text input for the scene visual prompt.",
    )
    prompts_render.add_argument(
        "--script-text",
        default="You probably missed this gaming detail, and here is the quick explanation.",
        help="Script text input for the narration direction prompt.",
    )
    prompts_render.add_argument(
        "--thumbnail-summary",
        default="Thumbnail concept summary for local publication-readiness review only.",
        help="Thumbnail summary input for the publication readiness review prompt.",
    )
    prompts_render.add_argument(
        "--narration-summary",
        default="Narration direction summary for local publication-readiness review only.",
        help="Narration summary input for the publication readiness review prompt.",
    )
    prompts_render.add_argument(
        "--evidence-review",
        default="Evidence review summary for local publication-readiness review only.",
        help="Evidence review input for the publication readiness review prompt.",
    )
    prompts_render.add_argument(
        "--platform",
        default="youtube_shorts",
        help="Platform identifier for the render helper.",
    )
    prompts_render.add_argument(
        "--duration",
        default=30,
        type=int,
        help="Target duration in seconds for the render helper.",
    )
    prompts_render.add_argument(
        "--show-content",
        action="store_true",
        help="Display the rendered prompt text. No provider call occurs.",
    )
    prompts_render.set_defaults(
        command_group="prompts",
        command_name="render",
        handler=_handle_prompts_render,
    )

    parsers_parser = subparsers.add_parser(
        "parsers",
        help="Inspect builtin prompt parser registrations.",
    )
    parsers_subparsers = parsers_parser.add_subparsers(dest="command_name")

    parsers_list = parsers_subparsers.add_parser(
        "list",
        help="List builtin parser registrations.",
    )
    parsers_list.set_defaults(
        command_group="parsers",
        command_name="list",
        handler=_handle_parsers_list,
    )

    parsers_validate = parsers_subparsers.add_parser(
        "validate",
        help="Validate builtin prompt/parser registry alignment.",
    )
    parsers_validate.set_defaults(
        command_group="parsers",
        command_name="validate",
        handler=_handle_parsers_validate,
    )

    run_parser = subparsers.add_parser("run", help="Run deterministic local demo workflows.")
    run_subparsers = run_parser.add_subparsers(dest="command_name")

    run_gaming = run_subparsers.add_parser(
        "gaming",
        help="Run the first executable deterministic demo gaming workflow.",
    )
    run_gaming.add_argument("--game", default="Minecraft", help="Game name for the local demo workflow.")
    run_gaming.add_argument("--topic", default="gaming facts", help="Topic for the local demo workflow.")
    run_gaming.add_argument(
        "--platform",
        default=ContentPlatform.YOUTUBE_SHORTS.value,
        choices=sorted(platform.value for platform in ContentPlatform),
        help="Publishing platform for the local demo workflow.",
    )
    run_gaming.add_argument(
        "--approve",
        action="store_true",
        help="Approve mock publishing so the local demo completes publishing.",
    )
    run_gaming.set_defaults(
        command_group="run",
        command_name="gaming",
        handler=_handle_run_gaming,
    )

    return parser


def _handle_config_validate(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Validate configuration without touching external systems."""

    del args, stderr
    settings = get_settings()
    _write_output(stdout, "Configuration is valid.")
    _write_rows(
        stdout,
        [
            ("application_name", settings.app_name),
            ("environment", settings.app_env),
            ("log_level", settings.log_level),
            ("default_llm_provider", settings.default_llm_provider),
        ],
    )
    return EXIT_SUCCESS


def _handle_config_show(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Display a safe configuration summary without exposing secrets."""

    del args, stderr
    summary = build_safe_config_summary()
    _write_rows(stdout, list(summary.items()))
    return EXIT_SUCCESS


def _handle_providers_list(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """List registered providers from the selected registry."""

    del stderr
    registry = _resolve_registry(use_mock=args.mock)
    providers = registry.list_providers()
    if not providers:
        _write_output(stdout, "No providers registered.")
        return EXIT_SUCCESS

    _write_output(stdout, "provider_type | name | version | capabilities")
    for provider in providers:
        _write_provider_row(stdout, provider_type=provider.provider_type, name=provider.name, version=provider.version or "unknown", capabilities=sorted(capability.value for capability in provider.capabilities))
    return EXIT_SUCCESS


def _handle_providers_health(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run health checks for all providers in the selected registry."""

    del stderr
    registry = _resolve_registry(use_mock=args.mock)
    providers = registry.list_providers()
    if not providers:
        _write_output(stdout, "No providers registered.")
        return EXIT_SUCCESS

    results = asyncio.run(_collect_provider_health(registry))
    all_healthy = True
    for provider_type, name, status in results:
        _write_output(stdout, f"{provider_type}/{name}: {status}")
        if status != "healthy":
            all_healthy = False

    return EXIT_SUCCESS if all_healthy else EXIT_RESOURCE_UNAVAILABLE


async def _collect_provider_health(
    registry,
) -> list[tuple[str, str, str]]:
    """Collect provider health states from a registry without exposing raw errors."""

    results: list[tuple[str, str, str]] = []
    for provider_info in registry.list_providers():
        provider = registry.get(provider_info.provider_type, provider_info.name)
        try:
            is_healthy = await provider.health_check()
        except CreatorOSError:
            status = "error"
        except Exception:  # noqa: BLE001
            status = "error"
        else:
            status = "healthy" if is_healthy else "unhealthy"
        results.append((provider_info.provider_type, provider_info.name, status))
    return results


def _handle_workflow_transitions(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Display allowed next workflow statuses for the supplied status."""

    del stderr
    status = WorkflowExecutionStatus(args.status)
    transitions = sorted(target.value for target in get_allowed_transitions(status))
    if not transitions:
        _write_output(stdout, "No transitions allowed.")
        return EXIT_SUCCESS

    _write_output(stdout, f"Allowed transitions for {status.value}:")
    for transition in transitions:
        _write_output(stdout, transition)
    return EXIT_SUCCESS


def _handle_workflow_demo_state(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Demonstrate workflow runtime state changes only."""

    del args, stderr
    execution = WorkflowExecution(workflow_id="demo_workflow", workflow_version=1, job_id="demo_job")
    runtime = WorkflowRuntime(execution)
    runtime.start()
    runtime.record_step_started("demo_step")
    runtime.record_step_completed("demo_step")
    final_execution = runtime.complete()

    _write_rows(
        stdout,
        [
            ("execution_id", final_execution.id),
            ("final_status", final_execution.status.value),
            ("recorded_events", len(runtime.events)),
        ],
    )
    return EXIT_SUCCESS


def _handle_prompts_manifest_show(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Display a safe summary of the prompt asset manifest."""

    del args, stderr
    manifest = PromptManifestLoader().load()
    _write_rows(
        stdout,
        [
            ("schema_version", manifest.schema_version),
            ("entries", len(manifest.entries)),
        ],
    )
    for entry in manifest.list_entries():
        _write_output(
            stdout,
            f"{entry.category.value} | {entry.name} | v{entry.version} | {entry.status.value} | {entry.path}",
        )
    return EXIT_SUCCESS


def _handle_prompts_manifest_validate(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Validate the prompt asset manifest against discovered prompt assets."""

    del args, stderr
    manifest = PromptManifestLoader().load()
    PromptAssetDiscovery().validate_manifest(manifest)
    _write_output(stdout, "Prompt manifest is valid.")
    _write_output(stdout, f"entries: {len(manifest.entries)}")
    return EXIT_SUCCESS


def _handle_prompts_discover(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Discover prompt assets and print a safe summary."""

    del args, stderr
    records = PromptAssetDiscovery().discover()
    _write_output(stdout, f"Discovered prompt assets: {len(records)}")
    for record in records:
        _write_output(
            stdout,
            f"{record.category.value} | {record.definition.name} | v{record.definition.version} | {record.relative_path}",
        )
    return EXIT_SUCCESS


def _handle_prompts_list(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """List builtin prompts without printing prompt contents."""

    del args, stderr
    registry = create_builtin_prompt_registry()
    manifest = PromptManifestLoader().load()
    category_by_identity = {
        (entry.name.casefold(), entry.version): entry.category.value for entry in manifest.list_entries()
    }

    _write_output(stdout, "name | version | status | category")
    for definition in registry.list_prompts():
        category = category_by_identity.get((definition.name.casefold(), definition.version), "unknown")
        _write_output(
            stdout,
            f"{definition.name} | v{definition.version} | {definition.status.value} | {category}",
        )
    return EXIT_SUCCESS


def _handle_prompts_render(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Render one supported builtin prompt locally without provider calls."""

    del stderr
    registry = create_builtin_prompt_registry()
    if args.prompt_name == GAMING_DISCOVER_TRENDS:
        rendered = render_gaming_discover_trends(
            registry,
            game=args.game,
            topic=args.topic,
            research_signals=args.signals,
            platform=args.platform,
            target_duration_seconds=args.duration,
        )
    elif args.prompt_name == YOUTUBE_SHORTS_SCRIPT:
        rendered = render_youtube_shorts_script(
            registry,
            title=args.title,
            game=args.game,
            topic=args.topic,
            angle=args.angle,
            hook_direction=args.hook_direction,
            platform=args.platform,
            target_duration_seconds=args.duration,
            source_summary=args.source_summary,
        )
    elif args.prompt_name == GAMING_HOOK:
        rendered = render_gaming_hook(
            registry,
            game=args.game,
            title=args.title,
            topic=args.topic,
            angle=args.angle,
            source_summary=args.source_summary,
            platform=args.platform,
        )
    elif args.prompt_name == GAMING_CTA:
        rendered = render_gaming_cta(
            registry,
            game=args.game,
            topic=args.topic,
            platform=args.platform,
            tone=args.tone,
        )
    elif args.prompt_name == STORYBOARD_SCENE_BREAKDOWN:
        rendered = render_storyboard_scene_breakdown(
            registry,
            title=args.title,
            game=args.game,
            platform=args.platform,
            hook=args.hook,
            body=args.body,
            ending=args.ending,
            call_to_action=args.call_to_action,
            target_duration_seconds=args.duration,
        )
    elif args.prompt_name == STORYBOARD_VISUAL_DIRECTION:
        rendered = render_storyboard_visual_direction(
            registry,
            game=args.game,
            scene_number=args.scene_number,
            scene_purpose=args.scene_purpose,
            script_beat=args.script_beat,
            visual_summary=args.visual_summary,
            platform=args.platform,
            duration_seconds=float(args.duration),
        )
    elif args.prompt_name == STORYBOARD_TIMING_REVIEW:
        rendered = render_storyboard_timing_review(
            registry,
            title=args.title,
            scene_summary=args.scene_summary,
            target_duration_seconds=args.duration,
            platform=args.platform,
        )
    elif args.prompt_name == GAMING_THUMBNAIL_CONCEPT:
        rendered = render_gaming_thumbnail_concept(
            registry,
            title=args.title,
            game=args.game,
            topic=args.topic,
            angle=args.angle,
            hook=args.hook,
            platform=args.platform,
            visual_context=args.visual_context,
        )
    elif args.prompt_name == GAMING_SCENE_VISUAL_PROMPT:
        rendered = render_gaming_scene_visual_prompt(
            registry,
            game=args.game,
            scene_number=args.scene_number,
            scene_purpose=args.scene_purpose,
            script_beat=args.script_beat,
            visual_direction=args.visual_direction,
            on_screen_text=args.on_screen_text,
            platform=args.platform,
        )
    elif args.prompt_name == GAMING_SCENE_MOTION_PROMPT:
        rendered = render_gaming_scene_motion_prompt(
            registry,
            game=args.game,
            scene_number=args.scene_number,
            scene_purpose=args.scene_purpose,
            visual_summary=args.visual_summary,
            script_beat=args.script_beat,
            duration_seconds=float(args.duration),
            platform=args.platform,
        )
    elif args.prompt_name == GAMING_NARRATION_DIRECTION:
        rendered = render_gaming_narration_direction(
            registry,
            title=args.title,
            game=args.game,
            script_text=args.script_text,
            target_duration_seconds=args.duration,
            tone=args.tone,
            platform=args.platform,
        )
    elif args.prompt_name == GAMING_SCRIPT_QUALITY_REVIEW:
        rendered = render_gaming_script_quality_review(
            registry,
            title=args.title,
            game=args.game,
            topic=args.topic,
            angle=args.angle,
            source_summary=args.source_summary,
            script_text=args.script_text,
            platform=args.platform,
            target_duration_seconds=args.duration,
        )
    elif args.prompt_name == GAMING_EVIDENCE_CONSISTENCY_REVIEW:
        rendered = render_gaming_evidence_consistency_review(
            registry,
            game=args.game,
            source_summary=args.source_summary,
            research_notes=args.research_notes,
            content_text=args.content_text,
            content_stage=args.content_stage,
        )
    elif args.prompt_name == GAMING_STORYBOARD_QUALITY_REVIEW:
        rendered = render_gaming_storyboard_quality_review(
            registry,
            title=args.title,
            game=args.game,
            script_text=args.script_text,
            storyboard_text=args.storyboard_text,
            platform=args.platform,
            target_duration_seconds=args.duration,
        )
    elif args.prompt_name == GAMING_PUBLICATION_READINESS_REVIEW:
        rendered = render_gaming_publication_readiness_review(
            registry,
            title=args.title,
            game=args.game,
            script_text=args.script_text,
            storyboard_summary=args.storyboard_summary,
            thumbnail_summary=args.thumbnail_summary,
            narration_summary=args.narration_summary,
            evidence_review=args.evidence_review,
            platform=args.platform,
        )
    else:
        raise CreatorOSValidationError(
            "the requested builtin prompt is not supported by the render command",
            code="prompt_render_cli_unsupported_prompt",
            details={"prompt_name": args.prompt_name},
        )

    _write_rows(
        stdout,
        [
            ("prompt_name", rendered.prompt_name),
            ("prompt_version", rendered.prompt_version),
            ("message_count", len(rendered.messages)),
            ("variable_names", ", ".join(sorted(rendered.variables))),
        ],
    )

    if args.show_content:
        _write_output(stdout, "Rendered locally only. No provider call occurred.")
        _write_output(stdout, rendered.text)

    return EXIT_SUCCESS


def _handle_run_gaming(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run the deterministic local demo gaming workflow with mock providers only."""

    del stderr
    workflow_input = GamingWorkflowInput(
        game=args.game,
        topic=args.topic,
        platform=ContentPlatform(args.platform),
        approve_publish=args.approve,
    )
    result = asyncio.run(
        run_demo_gaming_workflow(
            workflow_input,
            provider_registry=create_mock_provider_registry(),
        )
    )

    rows: list[tuple[str, object]] = [
        ("workflow", "local deterministic demo"),
        ("execution_id", result.execution.id),
        ("final_status", result.execution.status.value),
        ("selected_opportunity", result.opportunity.title),
        ("script_title", result.script.title),
        ("storyboard_scenes", len(result.storyboard.scenes)),
        ("generated_assets", len(result.generated_assets)),
    ]

    if result.approval_request is not None and not workflow_input.approve_publish:
        rows.append(("approval_request_id", result.approval_request.id))
        rows.append(("published", False))
    else:
        rows.append(("published", result.published_post is not None))
        if result.published_post is not None:
            rows.append(("published_post_id", result.published_post.id))
            rows.append(("published_url", result.published_post.url))

    _write_rows(stdout, rows)
    return EXIT_SUCCESS


def _handle_parsers_list(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """List builtin parser registrations without exposing prompt content."""

    del args, stderr
    registry = build_builtin_parser_registry()
    _write_output(stdout, "prompt_name | output_model")
    for prompt_name in registry.list_prompt_names():
        registration = registry.resolve(prompt_name)
        _write_output(
            stdout,
            f"{registration.prompt_name} | {registration.output_model_type.__name__}",
        )
    return EXIT_SUCCESS


def _handle_parsers_validate(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Validate builtin prompt/parser registry alignment without provider calls."""

    del args, stderr
    prompt_registry = create_builtin_prompt_registry()
    parser_registry = build_builtin_parser_registry()
    report = validate_builtin_prompt_parser_contracts(prompt_registry, parser_registry)

    _write_output(stdout, f"valid: {_format_value(report.valid)}")
    _write_output(stdout, f"prompt_count: {report.metadata['prompt_count']}")
    _write_output(stdout, f"parser_count: {report.metadata['parser_count']}")
    _write_output(
        stdout,
        f"missing_parsers: {', '.join(report.missing_parsers) if report.missing_parsers else '(none)'}",
    )
    _write_output(
        stdout,
        f"orphan_parsers: {', '.join(report.orphan_parsers) if report.orphan_parsers else '(none)'}",
    )
    return EXIT_SUCCESS if report.valid else EXIT_CONFIGURATION_ERROR


def build_safe_config_summary() -> dict[str, object]:
    """Return a safe configuration summary without secrets or raw connection strings."""

    settings = get_settings()
    database_summary = _parse_database_summary(settings.database_url)
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "debug": settings.debug,
        "log_level": settings.log_level,
        "database_driver": database_summary.driver,
        "database_host": database_summary.host,
        "database_name": database_summary.name,
        "default_llm_provider": settings.default_llm_provider,
        "provider_timeout_seconds": settings.provider_timeout_seconds,
        "provider_max_retries": settings.provider_max_retries,
        "assets_dir": str(settings.assets_dir),
        "logs_dir": str(settings.logs_dir),
        "prompts_dir": str(settings.prompts_dir),
        "openai_configured": _is_configured(settings.openai_api_key),
        "anthropic_configured": _is_configured(settings.anthropic_api_key),
        "youtube_configured": _is_configured(settings.youtube_client_id) and _is_configured(settings.youtube_client_secret),
    }


def _parse_database_summary(database_url: str) -> DatabaseSummary:
    """Extract safe database driver, host, and database name values from a URL."""

    try:
        parsed = urlsplit(database_url)
    except ValueError:
        return DatabaseSummary()

    if not parsed.scheme:
        return DatabaseSummary()

    database_name = parsed.path.lstrip("/").split("/")[-1] if parsed.path else "unknown"
    if not database_name:
        database_name = "unknown"

    host = parsed.hostname or "unknown"
    return DatabaseSummary(driver=parsed.scheme, host=host, name=database_name)


def _is_configured(value: str | None) -> bool:
    """Return whether an optional credential value is configured."""

    return value is not None and bool(value.strip())


def _resolve_registry(*, use_mock: bool):
    """Return the requested provider registry without mutating cached application state."""

    if use_mock:
        return create_mock_provider_registry()
    return get_provider_registry()


def _write_output(stream: TextIO, text: str) -> None:
    """Write a single line of normal CLI output."""

    stream.write(f"{text}\n")


def _write_error(stream: TextIO, text: str) -> None:
    """Write a single line of CLI error output."""

    stream.write(f"{text}\n")


def _write_rows(stream: TextIO, rows: list[tuple[str, object]]) -> None:
    """Render a plain-text list of key-value rows."""

    for key, value in rows:
        _write_output(stream, f"{key}: {_format_value(value)}")


def _write_provider_row(
    stream: TextIO,
    *,
    provider_type: str,
    name: str,
    version: str,
    capabilities: list[str],
) -> None:
    """Render one provider row in a predictable plain-text layout."""

    capability_text = ", ".join(capabilities)
    _write_output(stream, f"{provider_type} | {name} | {version} | {capability_text}")


def _format_value(value: object) -> str:
    """Render a value safely for plain-text CLI output."""

    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _classify_prompt_error_exit_code(error: PromptLoadError | PromptManifestError) -> int:
    """Map prompt manifest and discovery failures to stable CLI exit codes."""

    resource_unavailable_codes = {
        "prompt_load_file_not_found",
        "prompt_manifest_file_not_found",
        "prompt_manifest_mismatch",
    }
    if error.code in resource_unavailable_codes:
        return EXIT_RESOURCE_UNAVAILABLE
    return EXIT_CONFIGURATION_ERROR


def _normalize_system_exit_code(code: object) -> int:
    """Normalize argparse/SystemExit codes to a stable integer exit code."""

    if code is None:
        return EXIT_SUCCESS
    if isinstance(code, int):
        return code
    return EXIT_USAGE_ERROR
