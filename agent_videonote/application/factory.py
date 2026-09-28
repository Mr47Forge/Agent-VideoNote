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
    ProviderSpec,
    disabled_asr_runtime_config,
    load_asr_runtime_config,
)
from agent_videonote.core.config import RuntimeConfig, load_runtime_config
from agent_videonote.media.ffmpeg import FFmpegBackend
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
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


def build_runtime(
    *,
    profile: AsrProfile,
    provider_specs: tuple[ProviderSpec, ...] = (),
    config: RuntimeConfig | None = None,
) -> RuntimeContainer:
    runtime_config = config or load_runtime_config()
    store = JsonTaskStore(runtime_config.paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    media = FFmpegBackend(runtime_config)
    asr_registry = ProviderRegistry()
    cleanup_registry = CleanupRegistry()
    contexts = CourseContextRepository(runtime_config.paths.context / "courses")

    register_provider_specs(asr_registry, provider_specs)

    application = ApplicationService(
        config=runtime_config,
        tasks=tasks,
        workflow=workflow,
        media=media,
        asr_registry=asr_registry,
        asr_profile=profile,
        contexts=contexts,
    )
    visuals = VisualService(tasks, cleanup_registry)

    return RuntimeContainer(
        config=runtime_config,
        asr_registry=asr_registry,
        cleanup_registry=cleanup_registry,
        contexts=contexts,
        application=application,
        visuals=visuals,
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

    if config_path.is_file():
        asr_runtime = load_asr_runtime_config(config_path)
    else:
        asr_runtime = disabled_asr_runtime_config()

    return build_runtime(
        profile=asr_runtime.profile,
        provider_specs=asr_runtime.providers,
        config=runtime_config,
    )
