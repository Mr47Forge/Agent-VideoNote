from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_videonote.core.types import Artifact
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.workflow.context import build_workflow_context, workflow_context_key
from agent_videonote.workflow.stages import WorkflowStage


class TaskOperationsMixin:
    def task_dir(self, task_id: str) -> Path:
        return self.config.paths.tasks / task_id

    def prepare(self, source: str | Path) -> dict[str, Any]:
        state = self.tasks.create_or_resume(source)
        existing = state.artifacts.get("media_info")
        orphan_media = self.task_dir(state.task_id) / "source" / "media.json"
        if not existing and orphan_media.is_file():
            media_payload = read_json(orphan_media)
            state = self.tasks.register_artifact(
                state.task_id,
                "media_info",
                Artifact(kind="media_info", path=str(orphan_media)),
            )
            existing = state.artifacts.get("media_info")

        if existing and Path(existing["path"]).is_file():
            media_payload = read_json(existing["path"])
            if state.current_stage == WorkflowStage.INPUT.value:
                state = self.workflow.complete_current(
                    state.task_id,
                    expected_stage=WorkflowStage.INPUT,
                    evidence={
                        "source": state.source.path,
                        "media_info": str(existing["path"]),
                        "recovered": True,
                    },
                )
            return {"task": self._task_summary(state), "media": media_payload}

        info = self.media.probe(state.source.path)
        media_path = write_json_atomic(
            self.task_dir(state.task_id) / "source" / "media.json",
            asdict(info),
        )
        state = self.tasks.register_artifact(
            state.task_id,
            "media_info",
            Artifact(kind="media_info", path=str(media_path)),
        )

        if state.current_stage == WorkflowStage.INPUT.value:
            state = self.workflow.complete_current(
                state.task_id,
                expected_stage=WorkflowStage.INPUT,
                evidence={"source": state.source.path, "media_info": str(media_path)},
            )

        return {"task": self._task_summary(state), "media": asdict(info)}

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._task_summary(self.tasks.get(task_id))

    def get_task_context(self, task_id: str) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        stage = WorkflowStage(state.current_stage)
        return {
            "task": self._task_summary(state),
            "workflow": build_workflow_context(stage),
        }

    @staticmethod
    def _task_summary(state: Any) -> dict[str, Any]:
        artifact_counts: dict[str, int] = {}
        for artifact in state.artifacts.values():
            kind = str(artifact.get("kind") or "unknown")
            artifact_counts[kind] = artifact_counts.get(kind, 0) + 1

        unresolved_counts: dict[str, int] = {}
        for item in state.unresolved:
            category = str(item.get("category") or "unknown")
            unresolved_counts[category] = unresolved_counts.get(category, 0) + 1

        core_artifacts: dict[str, dict[str, Any]] = {}
        for name in ("media_info", "transcript", "delivery_report"):
            artifact = state.artifacts.get(name)
            if not artifact:
                continue
            item = {
                "kind": artifact.get("kind"),
                "path": artifact.get("path"),
            }
            if name == "transcript":
                metadata = artifact.get("metadata") or {}
                if metadata.get("course_id"):
                    item["course_id"] = metadata["course_id"]
            core_artifacts[name] = item

        stage = WorkflowStage(state.current_stage)
        return {
            "task_id": state.task_id,
            "source": state.source.path,
            "current_stage": stage.value,
            "context_key": workflow_context_key(stage),
            "context_tool": "task_context",
            "completed_stages": list(state.completed_stages),
            "core_artifacts": core_artifacts,
            "artifact_total": len(state.artifacts),
            "artifact_counts": artifact_counts,
            "unresolved_count": len(state.unresolved),
            "unresolved_counts": unresolved_counts,
            "event_count": len(state.events),
            "updated_at": state.updated_at,
        }
