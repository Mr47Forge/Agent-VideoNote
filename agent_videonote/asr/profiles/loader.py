from __future__ import annotations

import json
from pathlib import Path

from agent_videonote.asr.profiles.models import AsrProfile


def load_profile(path: str | Path) -> AsrProfile:
    source = Path(path).expanduser().resolve(strict=True)
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("ASR profile root must be an object")
    return AsrProfile.from_dict(data)
