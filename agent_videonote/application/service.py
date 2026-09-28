from __future__ import annotations

from agent_videonote.application.delivery_ops import DeliveryOperationsMixin
from agent_videonote.application.task_ops import TaskOperationsMixin
from agent_videonote.application.transcript_ops import TranscriptOperationsMixin
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig
from agent_videonote.media.interfaces import MediaBackend
from agent_videonote.tasks.service import TaskService
from agent_videonote.workflow.engine import WorkflowEngine


class ApplicationService(
    TaskOperationsMixin,
    TranscriptOperationsMixin,
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
    ):
        self.config = config
        self.tasks = tasks
        self.workflow = workflow
        self.media = media
        self.asr_registry = asr_registry
        self.asr_profile = asr_profile
        self.contexts = contexts
