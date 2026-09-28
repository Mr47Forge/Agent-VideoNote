from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent_videonote.media.types import MediaInfo


class MediaBackend(Protocol):
    def probe(self, source: str | Path) -> MediaInfo: ...

    def extract_audio(self, source: str | Path, output: str | Path) -> Path: ...

    def cut_audio(
        self,
        source: str | Path,
        output: str | Path,
        *,
        start: float,
        duration: float,
        speed: float = 1.0,
    ) -> Path: ...

    def extract_frame(self, source: str | Path, output: str | Path, *, second: float) -> Path: ...
