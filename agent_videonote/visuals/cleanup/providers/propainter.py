from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_videonote.visuals.cleanup.providers.common import (
    backend_metrics,
    explicit_mask_path,
    output_path,
    selected_provider,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig
from agent_videonote.visuals.setup import (
    FLOW_COMPLETION_EXPECTED_SIZE,
    PROPAINTER_EXPECTED_SIZE,
    RAFT_EXPECTED_SIZE,
)


_REQUIRED_WEIGHTS = {
    "raft-things.pth": RAFT_EXPECTED_SIZE,
    "recurrent_flow_completion.pth": FLOW_COMPLETION_EXPECTED_SIZE,
    "ProPainter.pth": PROPAINTER_EXPECTED_SIZE,
}


class ProPainterCleanupStrategy:
    """Use VSR's integrated ProPainter implementation in the one main venv."""

    strategy_id = "propainter"

    def __init__(self, runtime: VisualRuntimeConfig | None = None) -> None:
        self.runtime = runtime or VisualRuntimeConfig.disabled()
        paths = self.runtime.resolved_paths()
        self.root = paths["vsr_root"]
        self.model_dir = paths["propainter_model_dir"]

    def _problems(self) -> list[str]:
        problems: list[str] = []
        for module in ("torch", "torchvision", "numpy", "cv2", "PIL", "scipy", "einops", "matplotlib"):
            if importlib.util.find_spec(module) is None:
                problems.append(
                    f"Python dependency is missing from the Agent-VideoNote environment: {module}"
                )
        if self.root is None:
            problems.append("VSR source is not installed")
        elif not (self.root / "backend" / "inpaint" / "propainter_inpaint.py").is_file():
            problems.append(f"VSR ProPainter backend not found: {self.root}")
        if self.model_dir is None:
            problems.append("ProPainter model directory is not configured")
        else:
            missing = [
                name for name in _REQUIRED_WEIGHTS
                if not (self.model_dir / name).is_file()
            ]
            if missing:
                problems.append("ProPainter weights are missing: " + ", ".join(missing))
            for name, expected_size in _REQUIRED_WEIGHTS.items():
                path = self.model_dir / name
                if not path.is_file():
                    continue
                actual_size = path.stat().st_size
                if actual_size != expected_size:
                    problems.append(
                        f"ProPainter weight size mismatch for {name}: "
                        f"{actual_size} != {expected_size}"
                    )
        return problems

    def capabilities(self) -> dict[str, Any]:
        problems = self._problems()
        return {
            "strategy_id": self.strategy_id,
            "available": not problems,
            "kind": "video_inpaint",
            "requires_mask": True,
            "requires_gpu": True,
            "may_use_gpu": True,
            "external_runtime": True,
            "single_python": sys.executable,
            "automatic_text_removal": False,
            "reason": "; ".join(problems) if problems else None,
        }

    def preflight(self) -> list[str]:
        if self.root is None:
            return []
        return self._problems()

    def can_handle(self, request: CleanupRequest) -> bool:
        return (
            selected_provider(request, self.strategy_id)
            and explicit_mask_path(request) is not None
            and len(request.nearby_frame_paths) >= 3
        )

    def clean(self, request: CleanupRequest) -> CleanupResult:
        problems = self._problems()
        if problems:
            return CleanupResult(
                "unresolved",
                None,
                self.strategy_id,
                {
                    "unresolved_reason": "provider_unavailable",
                    "provider_reason": "; ".join(problems),
                },
            )
        mask = explicit_mask_path(request)
        if mask is None:
            return CleanupResult(
                "unresolved",
                None,
                self.strategy_id,
                {"unresolved_reason": "explicit_mask_required"},
            )
        frames = [Path(item).expanduser().resolve() for item in request.nearby_frame_paths]
        if len(frames) < 3 or any(not frame.is_file() for frame in frames):
            return CleanupResult(
                "unresolved",
                None,
                self.strategy_id,
                {"unresolved_reason": "propainter_requires_three_or_more_real_frames"},
            )
        target_index = min(
            len(frames) - 1,
            max(0, int(request.hints.get("target_index", len(frames) // 2))),
        )
        output = output_path(request, "propainter-clean").with_suffix(".png")
        output.parent.mkdir(parents=True, exist_ok=True)
        bridge = Path(__file__).with_name("_vsr_bridge.py").resolve()
        command = [
            sys.executable,
            str(bridge),
            "propainter",
            "--vsr-root", str(self.root),
            "--model-dir", str(self.model_dir),
            "--mask", str(mask),
            "--output", str(output),
            "--target-index", str(target_index),
            "--subvideo-length", str(max(10, int(request.hints.get("subvideo_length", 40)))),
            "--neighbor-length", str(max(2, int(request.hints.get("neighbor_length", 8)))),
            "--ref-stride", str(max(1, int(request.hints.get("ref_stride", 10)))),
            "--raft-iter", str(max(1, int(request.hints.get("raft_iter", 20)))),
        ]
        if request.hints.get("fp16", True):
            command.append("--fp16")
        for frame in frames:
            command.extend(["--frame", str(frame)])
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _failed(str(exc))
        if completed.returncode != 0 or not output.is_file():
            message = (completed.stderr or completed.stdout or "ProPainter failed").strip()
            return _failed(message[-1500:])
        return CleanupResult(
            "resolved",
            str(output),
            self.strategy_id,
            {
                "backend": "vsr-integrated-propainter",
                "single_python": sys.executable,
                "generated_pixels": True,
                "source_preserved": True,
                "fp16": bool(request.hints.get("fp16", True)),
                "frame_count": len(frames),
                "performance": backend_metrics(completed.stderr),
            },
        )


def _failed(reason: str) -> CleanupResult:
    return CleanupResult(
        "unresolved",
        None,
        "propainter",
        {
            "unresolved_reason": "provider_execution_failed",
            "provider_reason": reason,
        },
    )
