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


def next_stage(stage: WorkflowStage) -> WorkflowStage | None:
    index = ORDER.index(stage)
    if index + 1 >= len(ORDER):
        return None
    return ORDER[index + 1]
