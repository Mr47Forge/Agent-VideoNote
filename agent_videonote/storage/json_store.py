from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from agent_videonote.core.errors import TaskNotFoundError
from agent_videonote.tasks.models import TaskState


class JsonTaskStore:
    """Transparent, atomic file-based task persistence."""

    def __init__(self, tasks_root: Path):
        self.tasks_root = Path(tasks_root)
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def task_dir(self, task_id: str) -> Path:
        if not task_id or any(ch not in "0123456789abcdef" for ch in task_id.lower()):
            raise ValueError("invalid task_id")
        return self.tasks_root / task_id

    def state_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "state.json"

    def exists(self, task_id: str) -> bool:
        return self.state_path(task_id).is_file()

    def create(self, state: TaskState) -> TaskState:
        path = self.state_path(state.task_id)
        if path.exists():
            return self.load(state.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(path, state.to_dict())
        return state

    def load(self, task_id: str) -> TaskState:
        path = self.state_path(task_id)
        if not path.is_file():
            raise TaskNotFoundError(task_id)
        with path.open("r", encoding="utf-8") as handle:
            return TaskState.from_dict(json.load(handle))

    def save(self, state: TaskState) -> TaskState:
        path = self.state_path(state.task_id)
        if not path.parent.is_dir():
            raise TaskNotFoundError(state.task_id)
        self._write_atomic(path, state.to_dict())
        return state

    @staticmethod
    def _write_atomic(path: Path, data: dict) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
