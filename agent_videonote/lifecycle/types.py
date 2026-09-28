from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaUsage:
    name: str
    files: int
    bytes: int


@dataclass(frozen=True)
class TaskStorageReport:
    total_files: int
    total_bytes: int
    areas: tuple[AreaUsage, ...]
    truncated: bool = False


@dataclass(frozen=True)
class CleanupCandidate:
    path: str
    bytes: int
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    task_id: str
    candidates: tuple[CleanupCandidate, ...]

    @property
    def total_files(self) -> int:
        return len(self.candidates)

    @property
    def total_bytes(self) -> int:
        return sum(item.bytes for item in self.candidates)
