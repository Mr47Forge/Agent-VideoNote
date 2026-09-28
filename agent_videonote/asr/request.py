from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
