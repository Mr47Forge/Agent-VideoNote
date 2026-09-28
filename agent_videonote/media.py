from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import get_settings
from .tasks import load_task, task_root


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def source_path(task_id: str) -> Path:
    data = load_task(task_id)
    return Path(data["source"]["path"])


def probe(task_id: str) -> dict[str, Any]:
    settings = get_settings()
    src = source_path(task_id)
    proc = _run([
        settings.ffprobe,
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(src),
    ])
    return json.loads(proc.stdout)


def extract_audio(task_id: str) -> Path:
    settings = get_settings()
    root = task_root(task_id)
    out = root / "audio.wav"
    if out.is_file() and out.stat().st_size > 0:
        return out
    _run([
        settings.ffmpeg,
        "-i", str(source_path(task_id)),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(out),
        "-y",
    ])
    return out


def extract_slice(task_id: str, start: float, duration: float, name: str | None = None) -> Path:
    if start < 0 or duration <= 0 or duration > 180:
        raise ValueError("切片范围无效；duration 必须在 0-180 秒")
    settings = get_settings()
    root = task_root(task_id) / "arbitration"
    root.mkdir(parents=True, exist_ok=True)
    safe_name = name or f"{start:.3f}-{duration:.3f}.wav"
    safe_name = Path(safe_name).name
    if not safe_name.lower().endswith(".wav"):
        safe_name += ".wav"
    out = root / safe_name
    _run([
        settings.ffmpeg,
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(source_path(task_id)),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(out),
        "-y",
    ])
    return out


def extract_frame(task_id: str, second: float, name: str | None = None) -> Path:
    if second < 0:
        raise ValueError("时间不能小于 0")
    settings = get_settings()
    root = task_root(task_id) / "frames"
    root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(name or f"{second:.3f}.jpg").name
    if not safe_name.lower().endswith((".jpg", ".jpeg", ".png")):
        safe_name += ".jpg"
    out = root / safe_name
    _run([
        settings.ffmpeg,
        "-ss", f"{second:.3f}",
        "-i", str(source_path(task_id)),
        "-frames:v", "1",
        "-q:v", "2",
        str(out),
        "-y",
    ])
    return out
