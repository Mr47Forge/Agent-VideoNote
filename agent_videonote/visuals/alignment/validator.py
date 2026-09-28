from __future__ import annotations

from pathlib import Path

from agent_videonote.visuals.alignment.types import ImagePlacement


def validate_placements(markdown: str, placements: tuple[ImagePlacement, ...]) -> list[str]:
    problems: list[str] = []
    for item in placements:
        if not Path(item.image_path).is_file():
            problems.append(f"missing image: {item.image_path}")
        if item.anchor_text and item.anchor_text not in markdown:
            problems.append(f"anchor not found: {item.anchor_text[:80]}")
    return problems
