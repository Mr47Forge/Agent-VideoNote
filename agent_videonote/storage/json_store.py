from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable, Iterator

from agent_videonote.core.errors import TaskLockTimeoutError, TaskNotFoundError
from agent_videonote.tasks.models import TaskState


_LOCK_WAIT_SECONDS = 5.0
_LOCK_STALE_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02


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
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._state_lock(state.task_id):
            if path.exists():
                return self._load_unlocked(state.task_id)
            self._write_atomic(path, state.to_dict())
            return state

    def load(self, task_id: str) -> TaskState:
        return self._load_unlocked(task_id)

    def save(self, state: TaskState) -> TaskState:
        """Blind replacement under a short lock.

        Internal read-modify-write operations must use mutate() instead.
        """
        path = self.state_path(state.task_id)
        if not path.parent.is_dir():
            raise TaskNotFoundError(state.task_id)
        with self._state_lock(state.task_id):
            self._write_atomic(path, state.to_dict())
        return state

    def mutate(
        self,
        task_id: str,
        change: Callable[[TaskState], None],
    ) -> TaskState:
        """Atomically load, mutate and persist one task state across processes."""
        with self._state_lock(task_id):
            state = self._load_unlocked(task_id)
            change(state)
            self._write_atomic(self.state_path(task_id), state.to_dict())
            return state

    def _load_unlocked(self, task_id: str) -> TaskState:
        path = self.state_path(task_id)
        if not path.is_file():
            raise TaskNotFoundError(task_id)
        with path.open("r", encoding="utf-8") as handle:
            return TaskState.from_dict(json.load(handle))

    @contextmanager
    def _state_lock(self, task_id: str) -> Iterator[None]:
        task_dir = self.task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lock_path = task_dir / ".state.lock"
        token = uuid.uuid4().hex
        deadline = time.monotonic() + _LOCK_WAIT_SECONDS

        while True:
            try:
                fd = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                self._remove_stale_lock(lock_path)
                if time.monotonic() >= deadline:
                    raise TaskLockTimeoutError(
                        f"task state lock timed out: {task_id}; "
                        "another process may still be updating this task"
                    )
                time.sleep(_LOCK_POLL_SECONDS)
                continue

            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(token + "\n")
            break

        try:
            yield
        finally:
            try:
                current = lock_path.read_text(encoding="utf-8").strip()
                if current == token:
                    lock_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _remove_stale_lock(lock_path: Path) -> bool:
        try:
            before = lock_path.stat()
        except FileNotFoundError:
            return False

        if time.time() - before.st_mtime <= _LOCK_STALE_SECONDS:
            return False

        try:
            token = lock_path.read_text(encoding="utf-8")
            after = lock_path.stat()
        except FileNotFoundError:
            return False

        if (
            before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size
            or token != lock_path.read_text(encoding="utf-8")
        ):
            return False

        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            return False

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
