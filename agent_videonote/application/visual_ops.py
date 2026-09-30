from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.core.types import Artifact, SourceIdentity
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.visuals.cleanup.source_search import SourceFrameCleanup
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

    def clean_visual_candidate(self, task_id: str, candidate_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"vc-[0-9]{4,}", candidate_id):
            raise ValueError("invalid visual candidate id")
        state = self.tasks.get(task_id)
        task_dir = self.task_dir(task_id).resolve()
        manifest_path = task_dir / "visual" / "discovery" / "progress.json"
        artifact = state.artifacts.get("visual_discovery")
        if (artifact is None or Path(artifact["path"]).resolve() != manifest_path
                or not manifest_path.is_file()):
            raise FileNotFoundError("current task visual discovery artifact is unavailable")
        source = SourceIdentity.from_path(state.source.path)
        manifest = read_json(manifest_path)
        if (source.fingerprint != state.source.fingerprint
                or manifest.get("source_fingerprint") != source.fingerprint
                or Path(manifest.get("source_path", "")).resolve() != Path(source.path)):
            raise ValueError("visual candidate source does not match the current task")
        candidate = next((item for item in manifest.get("candidates", [])
                          if item.get("candidate_id") == candidate_id), None)
        if candidate is None:
            raise KeyError(f"visual candidate not found: {candidate_id}")
        image_path = Path(candidate["image_path"]).resolve(strict=True)
        timestamp = float(candidate["timestamp"])
        provenance = candidate.get("source_frame", {})
        duration = float(manifest["duration"])
        if (image_path.parent != task_dir / "visual" / "candidates"
                or Path(provenance.get("video", "")).resolve() != Path(source.path)
                or abs(float(provenance.get("timestamp", -1)) - timestamp) > 0.001
                or not math.isfinite(timestamp) or not 0 <= timestamp < duration):
            raise ValueError("visual candidate provenance does not match the current task")

        result_path = task_dir / "visual" / "cleanup" / f"{candidate_id}.json"
        if result_path.is_file():
            record = read_json(result_path)
            if (record.get("source_fingerprint") != source.fingerprint
                    or record.get("original_image_path") != str(image_path)
                    or record.get("original_timestamp") != timestamp):
                raise ValueError("persisted cleanup result does not match the current candidate")
            if record["resolved"] and not Path(record["output_path"]).is_file():
                raise FileNotFoundError("persisted cleaned image is missing")
            self._register_cleanup_result(task_id, candidate_id, result_path, record)
            return self._cleanup_summary(record)

        if (state.current_stage != WorkflowStage.VISUAL.value
                or WorkflowStage.TRANSCRIPT.value not in state.completed_stages
                or not (transcript := state.artifacts.get("transcript"))
                or not Path(transcript["path"]).is_file()):
            raise InvalidTransitionError("visual cleanup requires a completed transcript task in visual stage")
        cleaner = SourceFrameCleanup(
            self.media, FFmpegFrameSampler(self.config.ffmpeg_bin),
            self.cleanup_registry,
        )
        output_path = task_dir / "visual" / "cleaned" / f"{candidate_id}.jpg"
        result = cleaner.clean(
            source=Path(source.path), candidate=candidate, duration=duration,
            temp_dir=task_dir / "temp" / "visual_cleanup" / candidate_id,
            output_path=output_path,
        )
        record = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "source_fingerprint": source.fingerprint,
            "original_timestamp": timestamp,
            "original_image_path": str(image_path),
            "replacement_timestamp": result.detail.get("replacement_timestamp"),
            "output_path": result.output_path,
            "strategy_id": result.strategy_id,
            "confidence": result.detail.get("confidence"),
            "evidence": result.detail.get("evidence", {}),
            "resolved": result.resolved,
            "unresolved_reason": result.detail.get("unresolved_reason"),
        }
        write_json_atomic(result_path, record)
        self._register_cleanup_result(task_id, candidate_id, result_path, record)
        return self._cleanup_summary(record)

    def _register_cleanup_result(self, task_id: str, candidate_id: str,
                                 result_path: Path, record: dict[str, Any]) -> None:
        state = self.tasks.get(task_id)
        if "visual_cleanup" not in state.artifacts:
            self.tasks.register_artifact(
                task_id, "visual_cleanup",
                Artifact(kind="visual_cleanup", path=str(result_path.parent)),
            )
        if (not record["resolved"]
                and not any(item.get("category") == "visual_cleanup"
                            and item.get("candidate_id") == candidate_id
                            for item in self.tasks.get(task_id).unresolved)):
            self.tasks.add_unresolved(
                task_id, "visual_cleanup",
                {"candidate_id": candidate_id,
                 "reason": record["unresolved_reason"],
                 "record_path": str(result_path)},
            )

    @staticmethod
    def _cleanup_summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": record["candidate_id"],
            "resolved": record["resolved"],
            "strategy": record["strategy_id"],
            "original_timestamp": record["original_timestamp"],
            "replacement_timestamp": record["replacement_timestamp"],
            "output_path": record["output_path"],
            "unresolved_reason": record["unresolved_reason"],
        }
