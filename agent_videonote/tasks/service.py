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
        self.store = store

    def create_or_resume(self, source_path: str | Path) -> TaskState:
        source = SourceIdentity.from_path(source_path)
        task_id = task_id_for_source(source)
        if self.store.exists(task_id):
            return self.store.load(task_id)
        state = TaskState.new(task_id, source, WorkflowStage.INPUT.value)
        return self.store.create(state)

    def get(self, task_id: str) -> TaskState:
        return self.store.load(task_id)

    def register_artifact(self, task_id: str, name: str, artifact: Artifact) -> TaskState:
        state = self.store.load(task_id)
        state.artifacts[name] = artifact.to_dict()
        state.add_event("artifact.registered", {"name": name, "kind": artifact.kind})
        return self.store.save(state)

    def add_unresolved(self, task_id: str, category: str, detail: dict[str, Any]) -> TaskState:
        state = self.store.load(task_id)
        item = {"category": category, **detail}
        state.unresolved.append(item)
        state.add_event("unresolved.added", {"category": category})
        return self.store.save(state)
