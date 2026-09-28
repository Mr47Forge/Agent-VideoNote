from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    model_dir: Path
    task_dir: Path
    hotwords_file: Path
    ffmpeg: str
    ffprobe: str


def _default_data_dir() -> Path:
    local = os.getenv("LOCALAPPDATA")
    if local:
        return Path(local) / "Agent-VideoNote" / "data"
    return Path.home() / ".agent-videonote" / "data"


def get_settings() -> Settings:
    data_dir = Path(os.getenv("AGENT_VIDEONOTE_DATA_DIR", str(_default_data_dir()))).expanduser()
    model_dir = Path(
        os.getenv("AGENT_VIDEONOTE_MODEL_DIR", str(data_dir / "models"))
    ).expanduser()
    task_dir = data_dir / "workflow-tasks"
    hotwords_file = data_dir / "asr-context" / "hotwords.txt"

    ffmpeg = os.getenv("AGENT_VIDEONOTE_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = os.getenv("AGENT_VIDEONOTE_FFPROBE") or shutil.which("ffprobe") or "ffprobe"

    task_dir.mkdir(parents=True, exist_ok=True)
    hotwords_file.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        data_dir=data_dir,
        model_dir=model_dir,
        task_dir=task_dir,
        hotwords_file=hotwords_file,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
    )
