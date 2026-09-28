from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent_videonote.visuals.discovery.types import VisualState


class VisualDiscoveryStrategy(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def discover(self, source: str | Path, work_dir: str | Path) -> tuple[VisualState, ...]: ...
