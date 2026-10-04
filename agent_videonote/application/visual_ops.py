from __future__ import annotations

import hashlib
import math
import re
import shutil
import time
from pathlib import Path
from typing import Any

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.core.types import Artifact, SourceIdentity
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.visuals.cleanup.source_search import SourceFrameCleanup
from agent_videonote.visuals.cleanup.types import CleanupRequest
from agent_videonote.visuals.discovery.scene import (
    DiscoveryConfig,
    FFmpegFrameSampler,
    SceneContentDiscovery,
    read_candidates,
)
from agent_videonote.workflow.stages import WorkflowStage


class VisualOperationsMixin:
    def discover_visuals(self, task_id: str, *, budget_seconds: float = 600.0,
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
        reused = bool(manifest_path.is_file() and read_json(manifest_path).get("complete"))
        if config is None and manifest_path.is_file():
            config = read_json(manifest_path)["config"]
        scanner = SceneContentDiscovery(
            self.media, FFmpegFrameSampler(self.config.ffmpeg_bin),
            DiscoveryConfig(**(config or {})),
        )
        started = time.perf_counter()
        result = scanner.scan(
            source=Path(source.path), fingerprint=source.fingerprint,
            duration=info.duration, visual_dir=self.task_dir(task_id) / "visual",
            budget_seconds=budget_seconds,
        )
        elapsed = time.perf_counter() - started
        if "visual_discovery" not in state.artifacts:
            self.tasks.register_artifact(
                task_id, "visual_discovery",
                Artifact(kind="visual_discovery", path=result["artifact_path"]),
            )
        result["unresolved_count"] = len(self.tasks.get(task_id).unresolved)
        result["elapsed_seconds"] = round(elapsed, 3)
        result["reused"] = reused
        result["remaining_duration"] = round(
            max(0.0, float(result["total_duration"]) - float(result["scanned_duration"])), 3
        )
        return result

    def clean_visual_candidates(
        self,
        task_id: str,
        *,
        start: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        if start < 0 or not 1 <= limit <= 50:
            raise ValueError("start must be nonnegative and limit must be between 1 and 50")
        page = self.get_visual_candidates(task_id, start=start, limit=limit)
        started = time.perf_counter()
        counts = {"clean": 0, "resolved": 0, "unresolved": 0}
        resolved: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        reused_count = 0
        for item in page["candidates"]:
            candidate_id = str(item["candidate_id"])
            record_path = self.task_dir(task_id) / "visual" / "cleanup" / f"{candidate_id}.json"
            if record_path.is_file():
                reused_count += 1
            result = self.clean_visual_candidate(task_id, candidate_id)
            status = str(result["status"])
            counts[status] = counts.get(status, 0) + 1
            if status == "resolved":
                resolved.append({
                    "candidate_id": candidate_id,
                    "output_path": result.get("output_path"),
                    "replacement_timestamp": result.get("replacement_timestamp"),
                })
            elif status == "unresolved":
                unresolved.append({
                    "candidate_id": candidate_id,
                    "reason": result.get("unresolved_reason"),
                })
        processed = len(page["candidates"])
        next_start = start + processed
        return {
            "total": page["total"],
            "start": start,
            "processed": processed,
            "has_more": next_start < page["total"],
            "next_start": next_start if next_start < page["total"] else None,
            "counts": counts,
            "reused_count": reused_count,
            "resolved": resolved,
            "unresolved": unresolved,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

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
        legacy_record = None
        if result_path.is_file():
            record = read_json(result_path)
            if (record.get("source_fingerprint") != source.fingerprint
                    or record.get("original_image_path") != str(image_path)
                    or record.get("original_timestamp") != timestamp):
                raise ValueError("persisted cleanup result does not match the current candidate")
            if record.get("status") == "resolved" or ("status" not in record and record["resolved"]):
                if not record.get("output_path") or not Path(record["output_path"]).is_file():
                    raise FileNotFoundError("persisted cleaned image is missing")
            elif record.get("status") == "clean" and not image_path.is_file():
                raise FileNotFoundError("original visual candidate is missing")
            if record.get("status") in ("clean", "resolved") or ("status" not in record and record["resolved"]):
                self._register_cleanup_result(task_id, candidate_id, result_path, record)
                return self._cleanup_summary(record)
            if record.get("status") == "unresolved":
                self._register_cleanup_result(task_id, candidate_id, result_path, record)
                return self._cleanup_summary(record)
            if record.get("resolved") is not False or record.get("schema_version") != 1:
                raise ValueError("unknown persisted cleanup result schema")
            legacy_record = record

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
            "schema_version": 2,
            "candidate_id": candidate_id,
            "source_fingerprint": source.fingerprint,
            "original_timestamp": timestamp,
            "original_image_path": str(image_path),
            "replacement_timestamp": result.detail.get("replacement_timestamp"),
            "output_path": result.output_path,
            "strategy_id": result.strategy_id,
            "confidence": result.detail.get("confidence"),
            "evidence": result.detail.get("evidence", {}),
            "status": result.status,
            "resolved": result.resolved,
            "unresolved_reason": result.detail.get("unresolved_reason"),
        }
        if legacy_record is not None:
            backup_path = result_path.with_suffix(".phase1.json")
            if not backup_path.exists():
                shutil.copy2(result_path, backup_path)
        write_json_atomic(result_path, record)
        self._register_cleanup_result(task_id, candidate_id, result_path, record)
        return self._cleanup_summary(record)

    def repair_visual_candidate(
        self,
        task_id: str,
        candidate_id: str,
        *,
        provider: str,
        mask_path: str,
        window_seconds: float = 3.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        """Run an explicitly selected generated-pixel provider with an explicit mask."""
        if not re.fullmatch(r"vc-[0-9]{4,}", candidate_id):
            raise ValueError("invalid visual candidate id")
        if not re.fullmatch(r"[a-z0-9-]{2,40}", provider):
            raise ValueError("invalid cleanup provider id")
        if not 1.0 <= window_seconds <= 6.0:
            raise ValueError("window_seconds must be between 1 and 6")
        if not 0.5 <= interval <= 2.0:
            raise ValueError("interval must be between 0.5 and 2 seconds")

        capabilities = {
            item["strategy_id"]: item for item in self.cleanup_registry.capabilities()
        }
        selected = capabilities.get(provider)
        if selected is None or not selected.get("requires_mask"):
            raise ValueError(f"cleanup provider cannot be used for masked repair: {provider}")

        mask = Path(mask_path).expanduser().resolve(strict=True)
        state = self.tasks.get(task_id)
        if (state.current_stage != WorkflowStage.VISUAL.value
                or WorkflowStage.TRANSCRIPT.value not in state.completed_stages):
            raise InvalidTransitionError(
                "masked visual repair requires a completed transcript task in visual stage"
            )

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
        candidate = next(
            (item for item in manifest.get("candidates", [])
             if item.get("candidate_id") == candidate_id),
            None,
        )
        if candidate is None:
            raise KeyError(f"visual candidate not found: {candidate_id}")

        image_path = Path(candidate["image_path"]).resolve(strict=True)
        timestamp = float(candidate["timestamp"])
        duration = float(manifest["duration"])
        provenance = candidate.get("source_frame", {})
        if (image_path.parent != task_dir / "visual" / "candidates"
                or Path(provenance.get("video", "")).resolve() != Path(source.path)
                or abs(float(provenance.get("timestamp", -1)) - timestamp) > 0.001
                or not math.isfinite(timestamp) or not 0 <= timestamp < duration):
            raise ValueError("visual candidate provenance does not match the current task")

        mask_hash = _file_sha256(mask)
        repair_dir = task_dir / "visual" / "repairs"
        key = f"{candidate_id}.{provider}.{mask_hash[:12]}"
        record_path = repair_dir / f"{key}.json"
        if record_path.is_file():
            record = read_json(record_path)
            if (record.get("source_fingerprint") != source.fingerprint
                    or record.get("mask_sha256") != mask_hash
                    or record.get("provider") != provider):
                raise ValueError("persisted visual repair result does not match request")
            if record.get("status") == "resolved":
                output = record.get("output_path")
                if not output or not Path(output).is_file():
                    raise FileNotFoundError("persisted repaired image is missing")
                return _repair_summary(record)

        output_path = task_dir / "visual" / "repaired" / (
            f"{candidate_id}.{provider}{image_path.suffix.lower() or '.jpg'}"
        )
        temp_dir = task_dir / "temp" / "visual_repair" / key
        nearby: list[str] = []
        target_index = 0
        try:
            if provider in ("vsr-sttn", "propainter"):
                temp_dir.mkdir(parents=True, exist_ok=True)
                start = max(0.0, timestamp - window_seconds)
                end = min(duration, timestamp + window_seconds)
                entries: list[tuple[float, str]] = [(timestamp, str(image_path))]
                second = start
                sample_index = 0
                while second <= end + 1e-6 and len(entries) < 15:
                    if abs(second - timestamp) >= interval * 0.4:
                        frame = temp_dir / f"nearby-{sample_index:02d}-{second:.3f}.jpg"
                        self.media.extract_frame(source.path, frame, second=second)
                        entries.append((second, str(frame)))
                        sample_index += 1
                    second += interval
                entries.sort(key=lambda item: item[0])
                nearby = [item[1] for item in entries]
                target_index = next(
                    index for index, (_, path) in enumerate(entries)
                    if path == str(image_path)
                )
                if len(nearby) < 3:
                    raise ValueError("temporal cleanup provider requires at least three task-source frames")

            request = CleanupRequest(
                image_path=str(image_path),
                source_video=str(source.path),
                output_path=str(output_path),
                state_id=candidate_id,
                nearby_frame_paths=tuple(nearby),
                hints={
                    "provider": provider,
                    "mask_path": str(mask),
                    "target_index": target_index,
                },
            )
            result = self.cleanup_registry.resolve(request)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        record = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "provider": provider,
            "source_fingerprint": source.fingerprint,
            "original_timestamp": timestamp,
            "original_image_path": str(image_path),
            "mask_path": str(mask),
            "mask_sha256": mask_hash,
            "status": result.status,
            "resolved": result.resolved,
            "output_path": result.output_path,
            "detail": result.detail,
        }
        write_json_atomic(record_path, record)
        if "visual_repairs" not in self.tasks.get(task_id).artifacts:
            self.tasks.register_artifact(
                task_id,
                "visual_repairs",
                Artifact(kind="visual_repairs", path=str(repair_dir)),
            )
        return _repair_summary(record)

    def _register_cleanup_result(self, task_id: str, candidate_id: str,
                                 result_path: Path, record: dict[str, Any]) -> None:
        state = self.tasks.get(task_id)
        if "visual_cleanup" not in state.artifacts:
            self.tasks.register_artifact(
                task_id, "visual_cleanup",
                Artifact(kind="visual_cleanup", path=str(result_path.parent)),
            )
        if record.get("status") == "unresolved" and not any(
                item.get("category") == "visual_cleanup"
                and item.get("candidate_id") == candidate_id
                for item in self.tasks.get(task_id).unresolved):
            self.tasks.add_unresolved(
                task_id, "visual_cleanup",
                {"candidate_id": candidate_id,
                 "reason": record["unresolved_reason"],
                 "record_path": str(result_path)},
            )
        elif record.get("status") in ("clean", "resolved") or record.get("resolved") is True:
            if any(item.get("category") == "visual_cleanup"
                   and item.get("candidate_id") == candidate_id
                   for item in self.tasks.get(task_id).unresolved):
                self.tasks.remove_unresolved(task_id, "visual_cleanup", candidate_id)

    @staticmethod
    def _cleanup_summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": record["candidate_id"],
            "status": record.get("status", "resolved" if record["resolved"] else "unresolved"),
            "resolved": record["resolved"],
            "strategy": record["strategy_id"],
            "original_timestamp": record["original_timestamp"],
            "replacement_timestamp": record["replacement_timestamp"],
            "output_path": record["output_path"],
            "unresolved_reason": record["unresolved_reason"],
        }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repair_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": record["candidate_id"],
        "provider": record["provider"],
        "status": record["status"],
        "resolved": record["resolved"],
        "original_timestamp": record["original_timestamp"],
        "output_path": record["output_path"],
        "mask_sha256": record["mask_sha256"],
        "unresolved_reason": record.get("detail", {}).get("unresolved_reason"),
    }
