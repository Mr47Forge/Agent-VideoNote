from __future__ import annotations

import shutil
from pathlib import Path

from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


class SourceFrameReplacementStrategy:
    """Use a verified clean frame from the same visual state without synthesis."""

    strategy_id = "source-frame-replacement"

    def can_handle(self, request: CleanupRequest) -> bool:
        clean = request.hints.get("clean_frame_path")
        if not isinstance(clean, str) or not clean.strip():
            return False

        clean_path = Path(clean).expanduser().resolve()
        allowed = {Path(item).expanduser().resolve() for item in request.nearby_frame_paths}
        return clean_path in allowed and clean_path.is_file()

    def clean(self, request: CleanupRequest) -> CleanupResult:
        clean_path = Path(str(request.hints["clean_frame_path"])).expanduser().resolve()
        source_image = Path(request.image_path).expanduser().resolve()

        output = (
            Path(request.output_path).expanduser().resolve()
            if request.output_path
            else source_image.with_name(f"{source_image.stem}.clean{source_image.suffix}")
        )
        output.parent.mkdir(parents=True, exist_ok=True)

        if clean_path == output:
            return CleanupResult(
                status="resolved",
                output_path=str(output),
                strategy_id=self.strategy_id,
                detail={"method": "verified-clean-source-frame", "copied": False},
            )

        shutil.copy2(clean_path, output)
        return CleanupResult(
            status="resolved",
            output_path=str(output),
            strategy_id=self.strategy_id,
            detail={
                "method": "verified-clean-source-frame",
                "source_frame": str(clean_path),
                "copied": True,
            },
        )
