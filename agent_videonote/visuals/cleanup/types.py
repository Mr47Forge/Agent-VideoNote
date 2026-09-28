from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CleanupRequest:
    image_path: str
    source_video: str
    output_path: str | None = None
    state_id: str | None = None
    nearby_frame_paths: tuple[str, ...] = ()
    hints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanupResult:
    status: str
    output_path: str | None
    strategy_id: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.status == "resolved"
