from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_videonote.visuals.cleanup.providers.common import (
    explicit_mask_path,
    output_path,
    resolve_executable,
    selected_provider,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


@dataclass(frozen=True)
class VsrProviderConfig:
    root: Path | None
    python_bin: str
    lama_model: Path | None
    sttn_model: Path | None
    timeout_seconds: int = 900

    @classmethod
    def from_environment(cls) -> "VsrProviderConfig":
        return cls(
            root=_env_path("AGENT_VIDEONOTE_VSR_ROOT"),
            python_bin=os.getenv("AGENT_VIDEONOTE_VSR_PYTHON", sys.executable),
            lama_model=_env_path("AGENT_VIDEONOTE_VSR_LAMA_MODEL"),
            sttn_model=_env_path("AGENT_VIDEONOTE_VSR_STTN_MODEL"),
            timeout_seconds=max(30, int(os.getenv("AGENT_VIDEONOTE_VSR_TIMEOUT", "900"))),
        )


class _VsrBase:
    backend = ""
    model_attr = ""
    kind = ""

    def __init__(self, config: VsrProviderConfig | None = None) -> None:
        self.config = config or VsrProviderConfig.from_environment()

    @property
    def _model(self) -> Path | None:
        return getattr(self.config, self.model_attr)

    def _problems(self) -> list[str]:
        if self.config.root is None:
            return ["VSR root is not configured"]
        if not (self.config.root / "backend" / "inpaint").is_dir():
            return [f"VSR backend not found: {self.config.root}"]
        if resolve_executable(self.config.python_bin) is None:
            return [f"VSR Python not found: {self.config.python_bin}"]
        model = self._model
        if model is None:
            return [f"{self.backend} model path is not configured"]
        if not model.is_file():
            return [f"{self.backend} model not found: {model}"]
        return []

    def capabilities(self) -> dict[str, Any]:
        problems = self._problems()
        return {
            "strategy_id": self.strategy_id,
            "available": not problems,
            "kind": self.kind,
            "requires_mask": True,
            "requires_gpu": self.backend == "sttn",
            "external_runtime": True,
            "automatic_text_removal": False,
            "reason": "; ".join(problems) if problems else None,
        }

    def preflight(self) -> list[str]:
        return [] if self.config.root is None else self._problems()

    def can_handle(self, request: CleanupRequest) -> bool:
        return selected_provider(request, self.strategy_id) and explicit_mask_path(request) is not None

    def _run(self, args: list[str], output: Path) -> CleanupResult:
        problems = self._problems()
        if problems:
            return CleanupResult(
                "unresolved", None, self.strategy_id,
                {"unresolved_reason": "provider_unavailable",
                 "provider_reason": "; ".join(problems)},
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        bridge = Path(__file__).with_name("_vsr_bridge.py").resolve()
        command = [self.config.python_bin, str(bridge), self.backend, *args]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True,
                timeout=self.config.timeout_seconds, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CleanupResult(
                "unresolved", None, self.strategy_id,
                {"unresolved_reason": "provider_execution_failed",
                 "provider_reason": str(exc)},
            )
        if completed.returncode != 0 or not output.is_file():
            message = (completed.stderr or completed.stdout or "VSR backend failed").strip()
            return CleanupResult(
                "unresolved", None, self.strategy_id,
                {"unresolved_reason": "provider_execution_failed",
                 "provider_reason": message[-1000:]},
            )
        return CleanupResult(
            "resolved", str(output), self.strategy_id,
            {"backend": self.backend, "external_runtime": True,
             "generated_pixels": True, "source_preserved": True},
        )


class VsrLamaCleanupStrategy(_VsrBase):
    strategy_id = "vsr-lama"
    backend = "lama"
    model_attr = "lama_model"
    kind = "image_inpaint"

    def clean(self, request: CleanupRequest) -> CleanupResult:
        mask = explicit_mask_path(request)
        if mask is None:
            return _mask_required(self.strategy_id)
        output = output_path(request, "lama-clean")
        return self._run([
            "--vsr-root", str(self.config.root),
            "--model", str(self._model),
            "--image", str(Path(request.image_path).expanduser().resolve()),
            "--mask", str(mask), "--output", str(output),
        ], output)


class VsrSttnCleanupStrategy(_VsrBase):
    strategy_id = "vsr-sttn"
    backend = "sttn"
    model_attr = "sttn_model"
    kind = "video_inpaint"

    def can_handle(self, request: CleanupRequest) -> bool:
        return super().can_handle(request) and len(request.nearby_frame_paths) >= 3

    def clean(self, request: CleanupRequest) -> CleanupResult:
        mask = explicit_mask_path(request)
        if mask is None:
            return _mask_required(self.strategy_id)
        frames = [Path(item).expanduser().resolve() for item in request.nearby_frame_paths]
        if len(frames) < 3 or any(not item.is_file() for item in frames):
            return CleanupResult(
                "unresolved", None, self.strategy_id,
                {"unresolved_reason": "sttn_requires_three_or_more_real_frames"},
            )
        target_index = min(
            len(frames) - 1, max(0, int(request.hints.get("target_index", len(frames) // 2)))
        )
        output = output_path(request, "sttn-clean")
        args = [
            "--vsr-root", str(self.config.root), "--model", str(self._model),
            "--mask", str(mask), "--output", str(output),
            "--target-index", str(target_index),
        ]
        for frame in frames:
            args.extend(["--frame", str(frame)])
        return self._run(args, output)


def _mask_required(strategy_id: str) -> CleanupResult:
    return CleanupResult("unresolved", None, strategy_id,
                         {"unresolved_reason": "explicit_mask_required"})


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else None
