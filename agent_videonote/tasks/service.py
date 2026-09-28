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
            state = self._store.load(task_id)
            if state.source.path != source.path or state.source.mtime_ns != source.mtime_ns:
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
                return self._store.save(state)
            return state

        state = TaskState.new(task_id, source, WorkflowStage.INPUT.value)
        return self._store.create(state)

    def get(self, task_id: str) -> TaskState:
        return self._store.load(task_id)

    def register_artifact(self, task_id: str, name: str, artifact: Artifact) -> TaskState:
        state = self._store.load(task_id)
        state.artifacts[name] = artifact.to_dict()
        state.add_event("artifact.registered", {"name": name, "kind": artifact.kind})
        return self._store.save(state)

    def add_unresolved(self, task_id: str, category: str, detail: dict[str, Any]) -> TaskState:
        state = self._store.load(task_id)
        item = {"category": category, **detail}
        state.unresolved.append(item)
        state.add_event("unresolved.added", {"category": category})
        return self._store.save(state)

    def record_event(
        self,
        task_id: str,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> TaskState:
        state = self._store.load(task_id)
        state.add_event(event_type, detail or {})
        return self._store.save(state)
