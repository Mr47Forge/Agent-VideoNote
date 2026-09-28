from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TimeRange:
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("start must be >= 0")
        if self.end <= self.start:
            raise ValueError("end must be greater than start")

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class SourceIdentity:
    path: str
    size: int
    mtime_ns: int

    @classmethod
    def from_path(cls, path: str | Path) -> "SourceIdentity":
        source = Path(path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise FileNotFoundError(source)
        stat = source.stat()
        return cls(path=str(source), size=stat.st_size, mtime_ns=stat.st_mtime_ns)


@dataclass
class Artifact:
    kind: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
