from __future__ import annotations

from pathlib import Path
from typing import Any

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
        source: str | Path,
        work_dir: str | Path,
        strategy: VisualDiscoveryStrategy,
    ) -> tuple[VisualState, ...]:
        states = strategy.discover(source, work_dir)
        state = self.tasks.get(task_id)
        state.add_event(
            "visual.discovery",
            {"strategy": strategy.strategy_id, "states": len(states)},
        )
        self.tasks.store.save(state)
        return states

    def clean(self, task_id: str, request: CleanupRequest) -> CleanupResult:
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
