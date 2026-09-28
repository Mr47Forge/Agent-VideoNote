from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from agent_videonote.lifecycle.types import AreaUsage, TaskStorageReport


def inspect_task_storage(
    task_dir: str | Path,
    *,
    max_files: int = 100_000,
) -> TaskStorageReport:
    root = Path(task_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    if max_files < 1:
        raise ValueError("max_files must be positive")

    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total_files = 0
    total_bytes = 0
    truncated = False

    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]

        for name in files:
            path = current_path / name
            if path.is_symlink():
                continue
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue

            try:
                relative = path.relative_to(root)
            except ValueError:
                continue

            area = relative.parts[0] if len(relative.parts) > 1 else "root"
            counts[area][0] += 1
            counts[area][1] += size
            total_files += 1
            total_bytes += size

            if total_files >= max_files:
                truncated = True
                break

        if truncated:
            break

    areas = tuple(
        AreaUsage(name=name, files=value[0], bytes=value[1])
        for name, value in sorted(counts.items())
    )
    return TaskStorageReport(
        total_files=total_files,
        total_bytes=total_bytes,
        areas=areas,
        truncated=truncated,
    )
