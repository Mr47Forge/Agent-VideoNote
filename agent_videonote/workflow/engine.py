from __future__ import annotations

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.storage.interfaces import TaskStore
from agent_videonote.tasks.models import TaskState
from agent_videonote.workflow.stages import WorkflowStage, next_stage


class WorkflowEngine:
    """Mechanical stage progression only. It does not judge transcript quality."""

    def __init__(self, store: TaskStore):
        self.store = store

    def complete_current(
        self,
        task_id: str,
        evidence: dict[str, object] | None = None,
        *,
        expected_stage: WorkflowStage | str | None = None,
    ) -> TaskState:
        expected = (
            WorkflowStage(expected_stage)
            if expected_stage is not None
            else None
        )

        def change(state: TaskState) -> None:
            current = WorkflowStage(state.current_stage)

            if expected is not None and current != expected:
                if expected.value in state.completed_stages:
                    return
                raise InvalidTransitionError(
                    f"stale workflow completion: expected {expected.value}, "
                    f"current stage is {current.value}"
                )

            if current == WorkflowStage.DONE:
                return

            if current.value not in state.completed_stages:
                state.completed_stages.append(current.value)

            following = next_stage(current)
            if following is None:
                raise InvalidTransitionError(f"no next stage after {current.value}")

            state.current_stage = following.value
            state.add_event(
                "workflow.stage_completed",
                {
                    "stage": current.value,
                    "next": following.value,
                    "evidence": evidence or {},
                },
            )

        return self.store.mutate(task_id, change)

    def mark_done(
        self,
        task_id: str,
        evidence: dict[str, object] | None = None,
    ) -> TaskState:
        def change(state: TaskState) -> None:
            if state.current_stage != WorkflowStage.DONE.value:
                raise InvalidTransitionError(
                    "task must reach delivery completion before DONE"
                )

            if WorkflowStage.DONE.value in state.completed_stages:
                return

            state.completed_stages.append(WorkflowStage.DONE.value)
            state.add_event("workflow.done", {"evidence": evidence or {}})

        return self.store.mutate(task_id, change)
