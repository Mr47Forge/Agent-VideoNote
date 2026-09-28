from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_FINGERPRINT_CHUNK_SIZE = 1024 * 1024


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
    fingerprint: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> "SourceIdentity":
        source = Path(path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise FileNotFoundError(source)
        stat = source.stat()
        return cls(
            path=str(source),
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            fingerprint=_quick_fingerprint(source, stat.st_size),
        )


@dataclass
class Artifact:
    kind: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quick_fingerprint(path: Path, size: int) -> str:
    """Hash bounded samples so moving a large video does not create a new task."""
    digest = hashlib.sha256()
    digest.update(b"agent-videonote-source-v1\0")
    digest.update(str(size).encode("ascii"))
    digest.update(b"\0")

    if size == 0:
        return digest.hexdigest()

    offsets = [0]
    if size > _FINGERPRINT_CHUNK_SIZE:
        middle = max(0, size // 2 - _FINGERPRINT_CHUNK_SIZE // 2)
        end = max(0, size - _FINGERPRINT_CHUNK_SIZE)
        offsets.extend([middle, end])

    seen: set[int] = set()
    with path.open("rb") as handle:
        for offset in offsets:
            if offset in seen:
                continue
            seen.add(offset)
            handle.seek(offset)
            digest.update(offset.to_bytes(8, "big", signed=False))
            digest.update(handle.read(_FINGERPRINT_CHUNK_SIZE))

    return digest.hexdigest()
