from __future__ import annotations

from pathlib import Path

from agent_videonote.tasks.service import TaskService
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult
from agent_videonote.visuals.discovery.interfaces import VisualDiscoveryStrategy
from agent_videonote.visuals.discovery.types import VisualState


class VisualService:
    def __init__(self, tasks: TaskService, cleanup: CleanupRegistry):
        self.tasks = tasks
        self.cleanup = cleanup

    def discover(
        self,
        task_id: str,
        *,
        work_dir: str | Path,
        strategy: VisualDiscoveryStrategy,
    ) -> tuple[VisualState, ...]:
        state = self.tasks.get(task_id)
        states = strategy.discover(state.source.path, work_dir)
        self.tasks.record_event(
            task_id,
            "visual.discovery",
            {"strategy": strategy.strategy_id, "states": len(states)},
        )
        return states

    def clean(self, task_id: str, request: CleanupRequest) -> CleanupResult:
        state = self.tasks.get(task_id)
        if Path(request.source_video).resolve() != Path(state.source.path).resolve():
            raise ValueError("cleanup request source does not match task source")

        result = self.cleanup.resolve(request)
        if not result.resolved:
            self.tasks.add_unresolved(
                task_id,
                "visual_cleanup",
                {
                    "image_path": request.image_path,
                    "source_video": request.source_video,
                    "state_id": request.state_id,
                    "attempts": result.detail.get("attempts", []),
                },
            )
        return result
