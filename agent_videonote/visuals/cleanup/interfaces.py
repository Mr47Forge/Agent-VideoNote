from __future__ import annotations

from typing import Protocol

from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


class CleanupStrategy(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def can_handle(self, request: CleanupRequest) -> bool: ...

    def clean(self, request: CleanupRequest) -> CleanupResult: ...
