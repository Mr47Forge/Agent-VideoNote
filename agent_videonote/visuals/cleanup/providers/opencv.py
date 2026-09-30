from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from agent_videonote.visuals.cleanup.providers.common import (
    explicit_mask_path,
    output_path,
    selected_provider,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


class OpenCVInpaintStrategy:
    """Small-mask inpainting through OpenCV. Never creates or guesses a mask."""

    strategy_id = "opencv"

    def capabilities(self) -> dict[str, Any]:
        available = importlib.util.find_spec("cv2") is not None
        return {
            "strategy_id": self.strategy_id,
            "available": available,
            "kind": "image_inpaint",
            "requires_mask": True,
            "requires_gpu": False,
            "external_runtime": False,
            "automatic_text_removal": False,
            "reason": None if available else "opencv-python is not installed",
        }

    def preflight(self) -> list[str]:
        return []

    def can_handle(self, request: CleanupRequest) -> bool:
        return selected_provider(request, self.strategy_id) and explicit_mask_path(request) is not None

    def clean(self, request: CleanupRequest) -> CleanupResult:
        try:
            import cv2
        except ImportError:
            return _unavailable("opencv-python is not installed")

        source = Path(request.image_path).expanduser().resolve()
        mask_path = explicit_mask_path(request)
        if mask_path is None:
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "explicit_mask_required"})

        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if image is None or mask is None:
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "image_or_mask_unreadable"})
        if image.shape[:2] != mask.shape[:2]:
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "mask_dimensions_mismatch"})

        _, binary = cv2.threshold(mask, 0, 255, cv2.THRESH_BINARY)
        if not bool(binary.any()):
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "empty_mask"})

        radius = min(9.0, max(1.0, float(request.hints.get("opencv_radius", 3.0))))
        method_name = str(request.hints.get("opencv_method", "telea")).lower()
        method = cv2.INPAINT_NS if method_name == "ns" else cv2.INPAINT_TELEA
        repaired = cv2.inpaint(image, binary, radius, method)

        target = output_path(request, "opencv-clean")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), repaired):
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "output_write_failed"})
        return CleanupResult(
            "resolved", str(target), self.strategy_id,
            {
                "method": method_name,
                "radius": radius,
                "mask_path": str(mask_path),
                "generated_pixels": True,
                "source_preserved": True,
            },
        )


def _unavailable(reason: str) -> CleanupResult:
    return CleanupResult(
        "unresolved", None, "opencv",
        {"unresolved_reason": "provider_unavailable", "provider_reason": reason},
    )
