from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_videonote.core.types import Artifact, SourceIdentity
from agent_videonote.storage.interfaces import TaskStore
from agent_videonote.tasks.identity import task_id_for_source
from agent_videonote.tasks.models import TaskState
from agent_videonote.workflow.stages import WorkflowStage


class TaskService:
    def __init__(self, store: TaskStore):
        self._store = store

    def create_or_resume(self, source_path: str | Path) -> TaskState:
        source = SourceIdentity.from_path(source_path)
        task_id = task_id_for_source(source)

        if self._store.exists(task_id):
            def update_source(state: TaskState) -> None:
                if (
                    state.source.path == source.path
                    and state.source.mtime_ns == source.mtime_ns
                ):
                    return

                previous_path = state.source.path
                state.source = source
                state.add_event(
                    "source.relocated_or_metadata_changed",
                    {
                        "previous_path": previous_path,
                        "current_path": source.path,
                        "fingerprint": source.fingerprint,
                    },
                )

            return self._store.mutate(task_id, update_source)

        state = TaskState.new(task_id, source, WorkflowStage.INPUT.value)
        return self._store.create(state)

    def get(self, task_id: str) -> TaskState:
        return self._store.load(task_id)

    def register_artifact(self, task_id: str, name: str, artifact: Artifact) -> TaskState:
        def change(state: TaskState) -> None:
            state.artifacts[name] = artifact.to_dict()
            state.add_event(
                "artifact.registered",
                {"name": name, "kind": artifact.kind},
            )

        return self._store.mutate(task_id, change)

    def add_unresolved(self, task_id: str, category: str, detail: dict[str, Any]) -> TaskState:
        def change(state: TaskState) -> None:
            item = {"category": category, **detail}
            state.unresolved.append(item)
            state.add_event("unresolved.added", {"category": category})

        return self._store.mutate(task_id, change)

    def remove_unresolved(self, task_id: str, category: str, candidate_id: str) -> TaskState:
        """Remove only a matching candidate issue, retaining other unresolved work."""
        def change(state: TaskState) -> None:
            retained = [item for item in state.unresolved
                        if not (item.get("category") == category
                                and item.get("candidate_id") == candidate_id)]
            if len(retained) != len(state.unresolved):
                state.unresolved = retained
                state.add_event("unresolved.reclassified",
                                {"category": category, "candidate_id": candidate_id})

        return self._store.mutate(task_id, change)

    def record_event(
        self,
        task_id: str,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> TaskState:
        def change(state: TaskState) -> None:
            state.add_event(event_type, detail or {})

        return self._store.mutate(task_id, change)
