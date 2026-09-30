from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_videonote.visuals.cleanup.providers.common import (
    explicit_mask_path,
    resolve_executable,
    selected_provider,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


_REQUIRED_WEIGHTS = (
    "raft-things.pth",
    "recurrent_flow_completion.pth",
    "ProPainter.pth",
)


@dataclass(frozen=True)
class ProPainterConfig:
    root: Path | None
    python_bin: str
    timeout_seconds: int = 1800
    fp16: bool = True
    subvideo_length: int = 40
    neighbor_length: int = 8
    ref_stride: int = 10
    raft_iter: int = 20

    @classmethod
    def from_environment(cls) -> "ProPainterConfig":
        value = os.getenv("AGENT_VIDEONOTE_PROPAINTER_ROOT")
        root = Path(value).expanduser().resolve() if value else None
        return cls(
            root=root,
            python_bin=os.getenv("AGENT_VIDEONOTE_PROPAINTER_PYTHON", sys.executable),
            timeout_seconds=max(60, int(os.getenv("AGENT_VIDEONOTE_PROPAINTER_TIMEOUT", "1800"))),
            fp16=os.getenv("AGENT_VIDEONOTE_PROPAINTER_FP16", "1") != "0",
            subvideo_length=max(10, int(os.getenv("AGENT_VIDEONOTE_PROPAINTER_SUBVIDEO", "40"))),
            neighbor_length=max(2, int(os.getenv("AGENT_VIDEONOTE_PROPAINTER_NEIGHBOR", "8"))),
            ref_stride=max(1, int(os.getenv("AGENT_VIDEONOTE_PROPAINTER_REF_STRIDE", "10"))),
            raft_iter=max(1, int(os.getenv("AGENT_VIDEONOTE_PROPAINTER_RAFT_ITER", "20"))),
        )


class ProPainterCleanupStrategy:
    """External ProPainter adapter. Never lets upstream auto-download weights."""

    strategy_id = "propainter"

    def __init__(self, config: ProPainterConfig | None = None) -> None:
        self.config = config or ProPainterConfig.from_environment()

    def _problems(self) -> list[str]:
        root = self.config.root
        if root is None:
            return ["ProPainter root is not configured"]
        script = root / "inference_propainter.py"
        if not script.is_file():
            return [f"ProPainter inference script not found: {script}"]
        if resolve_executable(self.config.python_bin) is None:
            return [f"ProPainter Python not found: {self.config.python_bin}"]
        missing = [name for name in _REQUIRED_WEIGHTS if not (root / "weights" / name).is_file()]
        if missing:
            return [
                "ProPainter weights are missing; automatic download is disabled: "
                + ", ".join(missing)
            ]
        return []

    def capabilities(self) -> dict[str, Any]:
        problems = self._problems()
        return {
            "strategy_id": self.strategy_id,
            "available": not problems,
            "kind": "video_inpaint",
            "requires_mask": True,
            "requires_gpu": True,
            "external_runtime": True,
            "automatic_text_removal": False,
            "reason": "; ".join(problems) if problems else None,
        }

    def preflight(self) -> list[str]:
        return [] if self.config.root is None else self._problems()

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
                "unresolved", None, self.strategy_id,
                {"unresolved_reason": "provider_unavailable",
                 "provider_reason": "; ".join(problems)},
            )
        mask = explicit_mask_path(request)
        if mask is None:
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "explicit_mask_required"})

        source = Path(request.image_path).expanduser().resolve()
        frames = [Path(item).expanduser().resolve() for item in request.nearby_frame_paths]
        if source not in frames:
            frames.insert(len(frames) // 2, source)
        if any(not frame.is_file() for frame in frames):
            return CleanupResult("unresolved", None, self.strategy_id,
                                 {"unresolved_reason": "one_or_more_source_frames_missing"})
        target_index = frames.index(source)

        with tempfile.TemporaryDirectory(prefix="agent-videonote-propainter-") as temp:
            work = Path(temp)
            inputs = work / "input"
            outputs = work / "outputs"
            inputs.mkdir()
            for index, frame in enumerate(frames):
                suffix = frame.suffix.lower() if frame.suffix else ".png"
                shutil.copy2(frame, inputs / f"{index:04d}{suffix}")

            script = self.config.root / "inference_propainter.py"
            command = [
                self.config.python_bin, str(script),
                "--video", str(inputs), "--mask", str(mask), "--output", str(outputs),
                "--mask_dilation", "4",
                "--subvideo_length", str(self.config.subvideo_length),
                "--neighbor_length", str(self.config.neighbor_length),
                "--ref_stride", str(self.config.ref_stride),
                "--raft_iter", str(self.config.raft_iter),
                "--save_frames",
            ]
            if self.config.fp16:
                command.append("--fp16")
            try:
                completed = subprocess.run(
                    command, cwd=str(self.config.root), capture_output=True, text=True,
                    timeout=self.config.timeout_seconds, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return _failed(str(exc))

            result = outputs / inputs.name / "frames" / f"{target_index:04d}.png"
            if completed.returncode != 0 or not result.is_file():
                message = (completed.stderr or completed.stdout or "ProPainter failed").strip()
                return _failed(message[-1000:])

            if request.output_path:
                target = Path(request.output_path).expanduser().resolve()
                if target.suffix.lower() != ".png":
                    target = target.with_suffix(".png")
            else:
                target = source.with_name(f"{source.stem}.propainter-clean.png")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result, target)

        return CleanupResult(
            "resolved", str(target), self.strategy_id,
            {"backend": "official-propainter", "external_runtime": True,
             "generated_pixels": True, "source_preserved": True,
             "fp16": self.config.fp16, "frame_count": len(frames)},
        )


def _failed(reason: str) -> CleanupResult:
    return CleanupResult(
        "unresolved", None, "propainter",
        {"unresolved_reason": "provider_execution_failed", "provider_reason": reason},
    )
