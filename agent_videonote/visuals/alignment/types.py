from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagePlacement:
    image_path: str
    anchor_text: str
    state_id: str | None = None
    source_second: float | None = None
