from __future__ import annotations

from enum import Enum


class WorkflowStage(str, Enum):
    INPUT = "input"
    TRANSCRIPT = "transcript"
    VISUAL = "visual"
    DELIVERY = "delivery"
    DONE = "done"


ORDER: tuple[WorkflowStage, ...] = (
    WorkflowStage.INPUT,
    WorkflowStage.TRANSCRIPT,
    WorkflowStage.VISUAL,
    WorkflowStage.DELIVERY,
    WorkflowStage.DONE,
)


RULE_RESOURCES: dict[WorkflowStage, str] = {
    WorkflowStage.INPUT: "10-input.md",
    WorkflowStage.TRANSCRIPT: "20-transcript.md",
    WorkflowStage.VISUAL: "30-visual.md",
    WorkflowStage.DELIVERY: "40-delivery.md",
}


def next_stage(stage: WorkflowStage) -> WorkflowStage | None:
    index = ORDER.index(stage)
    if index + 1 >= len(ORDER):
        return None
    return ORDER[index + 1]
