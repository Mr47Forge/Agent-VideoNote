from __future__ import annotations

from dataclasses import dataclass

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
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
    application: ApplicationService
    visuals: VisualService


def build_runtime(
    *,
    profile: AsrProfile,
    config: RuntimeConfig | None = None,
) -> RuntimeContainer:
    runtime_config = config or load_runtime_config()
    store = JsonTaskStore(runtime_config.paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    media = FFmpegBackend(runtime_config)
    asr_registry = ProviderRegistry()
    cleanup_registry = CleanupRegistry()

    application = ApplicationService(
        config=runtime_config,
        tasks=tasks,
        workflow=workflow,
        media=media,
        asr_registry=asr_registry,
        asr_profile=profile,
    )
    visuals = VisualService(tasks, cleanup_registry)

    return RuntimeContainer(
        config=runtime_config,
        asr_registry=asr_registry,
        cleanup_registry=cleanup_registry,
        application=application,
        visuals=visuals,
    )
