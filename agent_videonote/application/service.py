from __future__ import annotations

from agent_videonote.application.catalog_ops import CatalogOperationsMixin
from agent_videonote.application.delivery_ops import DeliveryOperationsMixin
from agent_videonote.application.health_ops import HealthOperationsMixin
from agent_videonote.application.lifecycle_ops import LifecycleOperationsMixin
from agent_videonote.application.setup_ops import SetupOperationsMixin
from agent_videonote.asr.catalog.service import ModelCatalogService
from agent_videonote.application.task_ops import TaskOperationsMixin
from agent_videonote.application.transcript_ops import TranscriptOperationsMixin
from agent_videonote.application.visual_ops import VisualOperationsMixin
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.runtime_config import AsrRuntimeConfig
from agent_videonote.core.config import RuntimeConfig
from pathlib import Path
from agent_videonote.media.interfaces import MediaBackend
from agent_videonote.tasks.service import TaskService
from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.workflow.engine import WorkflowEngine
from threading import RLock


class ApplicationService(
    CatalogOperationsMixin,
    HealthOperationsMixin,
    LifecycleOperationsMixin,
    SetupOperationsMixin,
    TaskOperationsMixin,
    TranscriptOperationsMixin,
    VisualOperationsMixin,
    DeliveryOperationsMixin,
):
    """Thin application facade composed from focused operation modules."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        tasks: TaskService,
        workflow: WorkflowEngine,
        media: MediaBackend,
        asr_registry: ProviderRegistry,
        asr_profile: AsrProfile,
        contexts: CourseContextRepository,
        model_catalog: ModelCatalogService | None = None,
        startup_warnings: tuple[str, ...] = (),
        asr_runtime: AsrRuntimeConfig | None = None,
        asr_config_path: Path | None = None,
        visual_config_path: Path | None = None,
        cleanup_registry: CleanupRegistry | None = None,
    ):
        self.config = config
        self.tasks = tasks
        self.workflow = workflow
        self.media = media
        self.asr_registry = asr_registry
        self.asr_profile = asr_profile
        self.contexts = contexts
        self.model_catalog = model_catalog or ModelCatalogService()
        self.startup_warnings = tuple(startup_warnings)
        self.asr_runtime = asr_runtime
        self.asr_config_path = asr_config_path
        self.visual_config_path = visual_config_path
        self.cleanup_registry = cleanup_registry or build_default_cleanup_registry()
        # One application-level gate coordinates GPU work across ASR and visual
        # providers. ASR's registry alone cannot see GPU work launched by visual
        # cleanup subprocesses.
        self._gpu_operation_lock = RLock()
