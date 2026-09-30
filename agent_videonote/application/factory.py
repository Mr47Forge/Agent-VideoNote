from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.factory import register_provider_specs
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.runtime_config import (
    AsrRuntimeConfig,
    ProviderSpec,
    disabled_asr_runtime_config,
    load_asr_runtime_config,
)
from agent_videonote.core.config import RuntimeConfig, load_runtime_config
from agent_videonote.core.errors import ConfigurationError
from agent_videonote.media.ffmpeg import FFmpegBackend
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig
from agent_videonote.visuals.service import VisualService
from agent_videonote.workflow.engine import WorkflowEngine


@dataclass
class RuntimeContainer:
    config: RuntimeConfig
    asr_registry: ProviderRegistry
    cleanup_registry: CleanupRegistry
    contexts: CourseContextRepository
    application: ApplicationService
    visuals: VisualService
    startup_warnings: tuple[str, ...] = ()


def build_runtime(
    *,
    profile: AsrProfile,
    provider_specs: tuple[ProviderSpec, ...] = (),
    config: RuntimeConfig | None = None,
    startup_warnings: tuple[str, ...] = (),
    tolerate_provider_errors: bool = False,
    asr_config_path: Path | None = None,
) -> RuntimeContainer:
    runtime_config = config or load_runtime_config()
    store = JsonTaskStore(runtime_config.paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    media = FFmpegBackend(runtime_config)
    asr_registry = ProviderRegistry()
    visual_runtime_path = runtime_config.paths.context / "visual-runtime.json"
    try:
        visual_runtime = VisualRuntimeConfig.load(visual_runtime_path)
    except (OSError, ValueError) as exc:
        visual_runtime = VisualRuntimeConfig.disabled()
        startup_warnings = tuple(startup_warnings) + (
            f"Visual runtime config disabled: {exc}",
        )
    cleanup_registry = build_default_cleanup_registry(visual_runtime)
    contexts = CourseContextRepository(runtime_config.paths.context / "courses")

    provider_warnings = register_provider_specs(
        asr_registry,
        provider_specs,
        tolerate_errors=tolerate_provider_errors,
    )
    all_startup_warnings = tuple(startup_warnings) + tuple(provider_warnings)

    application = ApplicationService(
        config=runtime_config,
        tasks=tasks,
        workflow=workflow,
        media=media,
        asr_registry=asr_registry,
        asr_profile=profile,
        contexts=contexts,
        startup_warnings=all_startup_warnings,
        asr_runtime=AsrRuntimeConfig(profile=profile, providers=provider_specs),
        asr_config_path=asr_config_path,
        visual_config_path=visual_runtime_path,
        cleanup_registry=cleanup_registry,
    )
    visuals = VisualService(tasks, cleanup_registry)

    return RuntimeContainer(
        config=runtime_config,
        asr_registry=asr_registry,
        cleanup_registry=cleanup_registry,
        contexts=contexts,
        application=application,
        visuals=visuals,
        startup_warnings=all_startup_warnings,
    )


def build_runtime_from_environment(
    *,
    config: RuntimeConfig | None = None,
) -> RuntimeContainer:
    runtime_config = config or load_runtime_config()
    explicit = os.getenv("AGENT_VIDEONOTE_ASR_CONFIG")
    config_path = (
        Path(explicit).expanduser()
        if explicit
        else runtime_config.paths.context / "asr-runtime.json"
    )

    startup_warnings: list[str] = []
    if config_path.is_file():
        try:
            asr_runtime = load_asr_runtime_config(config_path)
        except ConfigurationError as exc:
            startup_warnings.append(
                f"ASR runtime config disabled: {exc}"
            )
            asr_runtime = disabled_asr_runtime_config()
    else:
        asr_runtime = disabled_asr_runtime_config()

    return build_runtime(
        profile=asr_runtime.profile,
        provider_specs=asr_runtime.providers,
        config=runtime_config,
        startup_warnings=tuple(startup_warnings),
        tolerate_provider_errors=True,
        asr_config_path=config_path,
    )
