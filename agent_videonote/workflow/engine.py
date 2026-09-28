from __future__ import annotations

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.storage.interfaces import TaskStore
from agent_videonote.tasks.models import TaskState
from agent_videonote.workflow.stages import WorkflowStage, next_stage


class WorkflowEngine:
    """Mechanical stage progression only. It does not judge transcript quality."""

    def __init__(self, store: TaskStore):
        self.store = store

    def complete_current(self, task_id: str, evidence: dict[str, object] | None = None) -> TaskState:
        state = self.store.load(task_id)
        current = WorkflowStage(state.current_stage)

        if current == WorkflowStage.DONE:
            return state

        if current.value not in state.completed_stages:
            state.completed_stages.append(current.value)

        following = next_stage(current)
        if following is None:
            raise InvalidTransitionError(f"no next stage after {current.value}")

        state.current_stage = following.value
        state.add_event(
            "workflow.stage_completed",
            {"stage": current.value, "next": following.value, "evidence": evidence or {}},
        )
        return self.store.save(state)

    def mark_done(self, task_id: str, evidence: dict[str, object] | None = None) -> TaskState:
        state = self.store.load(task_id)
        if state.current_stage != WorkflowStage.DONE.value:
            raise InvalidTransitionError("task must reach delivery completion before DONE")
        if WorkflowStage.DONE.value not in state.completed_stages:
            state.completed_stages.append(WorkflowStage.DONE.value)
        state.add_event("workflow.done", {"evidence": evidence or {}})
        return self.store.save(state)
