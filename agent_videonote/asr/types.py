from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent_videonote.core.types import TimeRange


@dataclass(frozen=True)
class RecognitionContext:
    language: str | None = None
    hotwords: tuple[str, ...] = ()
    free_text: str | None = None


@dataclass(frozen=True)
class TranscriptionRequest:
    audio_path: Path
    context: RecognitionContext = RecognitionContext()
    source_range: TimeRange | None = None


@dataclass(frozen=True)
class TranscriptWord:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: tuple[TranscriptSegment, ...]
    provider_id: str
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
