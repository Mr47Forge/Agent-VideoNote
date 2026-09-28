from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    tasks: Path
    models: Path
    context: Path
    backups: Path


@dataclass(frozen=True)
class RuntimeConfig:
    paths: RuntimePaths
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"


def default_runtime_root() -> Path:
    explicit = os.getenv("AGENT_VIDEONOTE_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()

    local = os.getenv("LOCALAPPDATA")
    if local:
        return (Path(local) / "Agent-VideoNote" / "data").resolve()

    return (Path.home() / ".agent-videonote" / "data").resolve()


def load_runtime_config() -> RuntimeConfig:
    root = default_runtime_root()
    paths = RuntimePaths(
        root=root,
        tasks=root / "tasks",
        models=Path(os.getenv("AGENT_VIDEONOTE_MODEL_DIR", root / "models")).expanduser(),
        context=root / "context",
        backups=root / "backups",
    )
    for path in (paths.root, paths.tasks, paths.context, paths.backups):
        path.mkdir(parents=True, exist_ok=True)

    return RuntimeConfig(
        paths=paths,
        ffmpeg_bin=os.getenv("AGENT_VIDEONOTE_FFMPEG", "ffmpeg"),
        ffprobe_bin=os.getenv("AGENT_VIDEONOTE_FFPROBE", "ffprobe"),
    )
