from __future__ import annotations

import re
from pathlib import Path

from agent_videonote.transcripts.types import Transcript, TranscriptSegment


_BLOCK_RE = re.compile(
    r"(?:^|\n)\s*(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})[^\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def load_srt(path: str | Path, *, language: str | None = None) -> Transcript:
    source = Path(path).expanduser().resolve(strict=True)
    text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    segments: list[TranscriptSegment] = []

    for match in _BLOCK_RE.finditer(text):
        content = " ".join(line.strip() for line in match.group(4).splitlines() if line.strip())
        if not content:
            continue
        segments.append(TranscriptSegment(
            start=_timestamp(match.group(2)),
            end=_timestamp(match.group(3)),
            text=content,
        ))

    if not segments:
        raise ValueError(f"no SRT segments parsed: {source}")

    return Transcript(
        text="".join(segment.text for segment in segments),
        segments=tuple(segments),
        source_id="subtitle:srt",
        language=language,
        metadata={"path": str(source)},
    )


def _timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000
    )
