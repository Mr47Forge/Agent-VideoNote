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


class _VsrBase:
    backend = ""
    kind = ""
    requires_temporal_frames = False

    def __init__(self, runtime: VisualRuntimeConfig | None = None) -> None:
        self.runtime = runtime or VisualRuntimeConfig.disabled()
        paths = self.runtime.resolved_paths()
        self.root = paths["vsr_root"]

    def _dependency_problems(self) -> list[str]:
        modules = ("torch", "numpy", "cv2", "PIL")
        if self.requires_temporal_frames:
            modules += ("torchvision", "matplotlib")
        return [
            f"Python dependency is missing from the Agent-VideoNote environment: {name}"
            for name in modules
            if importlib.util.find_spec(name) is None
        ]

    def _model_problems(self) -> list[str]:
        return []

    def _problems(self) -> list[str]:
        problems = self._dependency_problems()
        if self.root is None:
            problems.append("VSR source is not installed")
        elif not (self.root / "backend" / "inpaint").is_dir():
            problems.append(f"VSR inpaint backend not found: {self.root}")
        problems.extend(self._model_problems())
        return problems

    def capabilities(self) -> dict[str, Any]:
        problems = self._problems()
        return {
            "strategy_id": self.strategy_id,
            "available": not problems,
            "kind": self.kind,
            "requires_mask": True,
            "requires_gpu": self.requires_temporal_frames,
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
        if not selected_provider(request, self.strategy_id):
            return False
        if explicit_mask_path(request) is None:
            return False
        if self.requires_temporal_frames and len(request.nearby_frame_paths) < 3:
            return False
        return True

    def _run(self, args: list[str], output: Path) -> CleanupResult:
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
        output.parent.mkdir(parents=True, exist_ok=True)
        bridge = Path(__file__).with_name("_vsr_bridge.py").resolve()
        command = [sys.executable, str(bridge), self.backend, *args]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=int(request_timeout(self.backend)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _failed(self.strategy_id, str(exc))
        if completed.returncode != 0 or not output.is_file():
            message = (completed.stderr or completed.stdout or "VSR backend failed").strip()
            return _failed(self.strategy_id, message[-1500:])
        return CleanupResult(
            "resolved",
            str(output),
            self.strategy_id,
            {
                "backend": self.backend,
                "single_python": sys.executable,
                "generated_pixels": True,
                "source_preserved": True,
                "performance": backend_metrics(completed.stderr),
            },
        )


class VsrLamaCleanupStrategy(_VsrBase):
    strategy_id = "vsr-lama"
    backend = "lama"
    kind = "image_inpaint"

    def __init__(self, runtime: VisualRuntimeConfig | None = None) -> None:
        super().__init__(runtime)
        self.model = self.runtime.resolved_paths()["lama_model"]

    def _model_problems(self) -> list[str]:
        if self.model is None:
            return ["Big-LaMa model is not installed"]
        return [] if self.model.is_file() else [f"Big-LaMa model not found: {self.model}"]

    def clean(self, request: CleanupRequest) -> CleanupResult:
        mask = explicit_mask_path(request)
        if mask is None:
            return _mask_required(self.strategy_id)
        output = output_path(request, "lama-clean")
        return self._run([
            "--vsr-root", str(self.root),
            "--model", str(self.model),
            "--image", str(Path(request.image_path).expanduser().resolve()),
            "--mask", str(mask),
            "--output", str(output),
        ], output)


class VsrSttnCleanupStrategy(_VsrBase):
    strategy_id = "vsr-sttn"
    backend = "sttn"
    kind = "video_inpaint"
    requires_temporal_frames = True

    def __init__(self, runtime: VisualRuntimeConfig | None = None) -> None:
        super().__init__(runtime)
        self.model = self.runtime.resolved_paths()["sttn_model"]

    def _model_problems(self) -> list[str]:
        if self.model is None:
            return ["STTN model is not installed"]
        return [] if self.model.is_file() else [f"STTN model not found: {self.model}"]

    def clean(self, request: CleanupRequest) -> CleanupResult:
        mask = explicit_mask_path(request)
        if mask is None:
            return _mask_required(self.strategy_id)
        frames = [Path(item).expanduser().resolve() for item in request.nearby_frame_paths]
        if len(frames) < 3 or any(not item.is_file() for item in frames):
            return CleanupResult(
                "unresolved",
                None,
                self.strategy_id,
                {"unresolved_reason": "sttn_requires_three_or_more_real_frames"},
            )
        target_index = min(
            len(frames) - 1,
            max(0, int(request.hints.get("target_index", len(frames) // 2))),
        )
        output = output_path(request, "sttn-clean")
        args = [
            "--vsr-root", str(self.root),
            "--model", str(self.model),
            "--mask", str(mask),
            "--output", str(output),
            "--target-index", str(target_index),
        ]
        for frame in frames:
            args.extend(["--frame", str(frame)])
        return self._run(args, output)


def request_timeout(backend: str) -> int:
    return 1800 if backend in ("sttn", "propainter") else 900


def _mask_required(strategy_id: str) -> CleanupResult:
    return CleanupResult(
        "unresolved",
        None,
        strategy_id,
        {"unresolved_reason": "explicit_mask_required"},
    )


def _failed(strategy_id: str, reason: str) -> CleanupResult:
    return CleanupResult(
        "unresolved",
        None,
        strategy_id,
        {
            "unresolved_reason": "provider_execution_failed",
            "provider_reason": reason,
        },
    )
