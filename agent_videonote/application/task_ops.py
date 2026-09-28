from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_videonote.core.types import Artifact
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.workflow.stages import WorkflowStage


class TaskOperationsMixin:
    def task_dir(self, task_id: str) -> Path:
        return self.config.paths.tasks / task_id

    def prepare(self, source: str | Path) -> dict[str, Any]:
        state = self.tasks.create_or_resume(source)
        existing = state.artifacts.get("media_info")
        if existing and Path(existing["path"]).is_file():
            media_payload = read_json(existing["path"])
            if state.current_stage == WorkflowStage.INPUT.value:
                state = self.workflow.complete_current(
                    state.task_id,
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
                evidence={"source": state.source.path, "media_info": str(media_path)},
            )

        return {"task": self._task_summary(state), "media": asdict(info)}

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._task_summary(self.tasks.get(task_id))

    @staticmethod
    def _task_summary(state: Any) -> dict[str, Any]:
        return {
            "task_id": state.task_id,
            "source": state.source.path,
            "current_stage": state.current_stage,
            "completed_stages": list(state.completed_stages),
            "artifacts": dict(state.artifacts),
            "unresolved_count": len(state.unresolved),
            "updated_at": state.updated_at,
        }

