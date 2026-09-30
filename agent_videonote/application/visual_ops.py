from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.core.types import Artifact, SourceIdentity
from agent_videonote.storage.artifacts import read_json
from agent_videonote.visuals.discovery.scene import (
    DiscoveryConfig,
    FFmpegFrameSampler,
    SceneContentDiscovery,
    read_candidates,
)
from agent_videonote.workflow.stages import WorkflowStage


class VisualOperationsMixin:
    def discover_visuals(self, task_id: str, *, budget_seconds: float = 120.0,
                         config: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        if (state.current_stage != WorkflowStage.VISUAL.value
                or WorkflowStage.TRANSCRIPT.value not in state.completed_stages
                or not (transcript := state.artifacts.get("transcript"))
                or not Path(transcript["path"]).is_file()):
            raise InvalidTransitionError("visual discovery requires a completed transcript task in visual stage")
        source = SourceIdentity.from_path(state.source.path)
        if source.fingerprint != state.source.fingerprint:
            raise ValueError("source video changed after task preparation")
        info = self.media.probe(source.path)
        if info.duration is None:
            raise ValueError("video duration is unavailable")
        manifest_path = self.task_dir(task_id) / "visual" / "discovery" / "progress.json"
        if config is None and manifest_path.is_file():
            config = read_json(manifest_path)["config"]
        scanner = SceneContentDiscovery(
            self.media, FFmpegFrameSampler(self.config.ffmpeg_bin),
            DiscoveryConfig(**(config or {})),
        )
        result = scanner.scan(
            source=Path(source.path), fingerprint=source.fingerprint,
            duration=info.duration, visual_dir=self.task_dir(task_id) / "visual",
            budget_seconds=budget_seconds,
        )
        if "visual_discovery" not in state.artifacts:
            self.tasks.register_artifact(
                task_id, "visual_discovery",
                Artifact(kind="visual_discovery", path=result["artifact_path"]),
            )
        result["unresolved_count"] = len(self.tasks.get(task_id).unresolved)
        return result

    def get_visual_candidates(self, task_id: str, *, start: int = 0,
                              limit: int = 20) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        artifact = state.artifacts.get("visual_discovery")
        if artifact is None or not Path(artifact["path"]).is_file():
            raise FileNotFoundError("visual discovery artifact is unavailable")
        return read_candidates(Path(artifact["path"]), start=start, limit=limit)
