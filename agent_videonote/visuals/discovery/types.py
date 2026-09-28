from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrameCandidate:
    second: float
    path: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisualState:
    state_id: str
    start: float
    end: float
    candidates: tuple[FrameCandidate, ...]
    description: str | None = None
