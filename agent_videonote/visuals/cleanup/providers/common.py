from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent_videonote.visuals.cleanup.types import CleanupRequest


def selected_provider(request: CleanupRequest, provider_id: str) -> bool:
    """Generated-pixel providers are opt-in only."""
    return request.hints.get("provider") == provider_id


def explicit_mask_path(request: CleanupRequest) -> Path | None:
    value = request.hints.get("mask_path")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(value).expanduser().resolve(strict=True)
    except FileNotFoundError:
        return None


def output_path(request: CleanupRequest, suffix: str) -> Path:
    source = Path(request.image_path).expanduser().resolve()
    if request.output_path:
        return Path(request.output_path).expanduser().resolve()
    return source.with_name(f"{source.stem}.{suffix}{source.suffix}")


def resolve_executable(value: str) -> str | None:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            return None
        return str(resolved) if resolved.is_file() else None
    found = shutil.which(value)
    return str(Path(found).resolve()) if found else None


def backend_metrics(stderr: str) -> dict:
    prefix = "AGENT_VIDEONOTE_METRICS="
    for line in reversed(stderr.splitlines()):
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                return {}
            return value if isinstance(value, dict) else {}
    return {}
