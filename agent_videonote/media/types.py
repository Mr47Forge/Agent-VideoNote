from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MediaStream:
    index: int
    kind: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    frame_rate: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaInfo:
    path: str
    duration: float | None
    format_name: str | None
    streams: tuple[MediaStream, ...]
