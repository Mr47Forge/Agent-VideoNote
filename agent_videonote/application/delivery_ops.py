from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.core.types import Artifact
from agent_videonote.delivery.validator import DeliveryReport, validate_delivery
from agent_videonote.storage.artifacts import write_json_atomic
from agent_videonote.workflow.stages import WorkflowStage


class DeliveryOperationsMixin:
    def complete_visual(self, task_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        if state.current_stage != WorkflowStage.VISUAL.value:
            raise InvalidTransitionError("task is not in visual stage")
        state = self.workflow.complete_current(task_id, evidence=evidence)
        return self._task_summary(state)

    def validate_and_finish_delivery(
        self,
        task_id: str,
        deliverables_dir: str | Path,
    ) -> DeliveryReport:
        state = self.tasks.get(task_id)
        if state.current_stage == WorkflowStage.DONE.value:
            report = validate_delivery(deliverables_dir)
            if report.ok and WorkflowStage.DONE.value not in state.completed_stages:
                self.workflow.mark_done(
                    task_id,
                    evidence={"validated": True, "recovered": True},
                )
            return report

        if state.current_stage != WorkflowStage.DELIVERY.value:
            raise InvalidTransitionError("task is not in delivery stage")

        report = validate_delivery(deliverables_dir)
        report_path = write_json_atomic(
            self.task_dir(task_id) / "delivery" / "report.json",
            {
                "ok": report.ok,
                "problems": list(report.problems),
                "image_references": list(report.image_references),
                "orphan_images": list(report.orphan_images),
                "unexpected_entries": list(report.unexpected_entries),
                "deliverables_dir": str(Path(deliverables_dir).resolve()),
            },
        )
        self.tasks.register_artifact(
            task_id,
            "delivery_report",
            Artifact(kind="delivery_report", path=str(report_path)),
        )

        if report.ok:
            self.workflow.complete_current(
                task_id,
                evidence={"delivery_report": str(report_path)},
            )
            self.workflow.mark_done(task_id, evidence={"validated": True})
        return report

