from __future__ import annotations

from agent_videonote.transcripts.types import Transcript


def validate_transcript(transcript: Transcript) -> list[str]:
    problems: list[str] = []
    previous_end = 0.0

    if not transcript.segments:
        problems.append("transcript has no segments")

    for index, segment in enumerate(transcript.segments, start=1):
        if segment.start < 0:
            problems.append(f"segment {index} starts before zero")
        if segment.end <= segment.start:
            problems.append(f"segment {index} has invalid duration")
        if segment.start < previous_end - 0.05:
            problems.append(f"segment {index} overlaps or is out of order")
        if not segment.text.strip():
            problems.append(f"segment {index} is empty")
        previous_end = max(previous_end, segment.end)

    return problems
