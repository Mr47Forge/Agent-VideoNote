from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _source_identity(source: Path) -> dict[str, Any]:
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise FileNotFoundError(f"不是文件: {source}")
    stat = source.stat()
    return {
        "path": os.path.normcase(str(source)),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _task_id(identity: dict[str, Any]) -> str:
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def create_or_resume_task(source: str) -> dict[str, Any]:
    settings = get_settings()
    source_path = Path(source)
    identity = _source_identity(source_path)
    task_id = _task_id(identity)
    root = settings.task_dir / task_id
    manifest_path = root / "task.json"

    if manifest_path.is_file():
        return load_task(task_id)

    root.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": 1,
        "task_id": task_id,
        "source": identity,
        "state": "DISCOVER",
        "created_at": _now(),
        "updated_at": _now(),
        "artifacts": {},
        "notes": {},
    }
    _write_json_atomic(manifest_path, data)
    return data


def task_root(task_id: str) -> Path:
    if not task_id or any(ch not in "0123456789abcdef" for ch in task_id.lower()):
        raise ValueError("非法 task_id")
    root = get_settings().task_dir / task_id
    if not root.is_dir():
        raise FileNotFoundError(f"任务不存在: {task_id}")
    return root


def manifest_path(task_id: str) -> Path:
    return task_root(task_id) / "task.json"


def load_task(task_id: str) -> dict[str, Any]:
    path = manifest_path(task_id)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def update_task(task_id: str, **changes: Any) -> dict[str, Any]:
    data = load_task(task_id)
    for key, value in changes.items():
        data[key] = value
    data["updated_at"] = _now()
    _write_json_atomic(manifest_path(task_id), data)
    return data


def set_artifact(task_id: str, name: str, value: str) -> dict[str, Any]:
    data = load_task(task_id)
    artifacts = dict(data.get("artifacts") or {})
    artifacts[name] = value
    data["artifacts"] = artifacts
    data["updated_at"] = _now()
    _write_json_atomic(manifest_path(task_id), data)
    return data
