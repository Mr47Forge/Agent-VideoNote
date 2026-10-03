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


RULE_FILES: dict[WorkflowStage, str] = {
    WorkflowStage.INPUT: "workflow/10-input.md",
    WorkflowStage.TRANSCRIPT: "workflow/20-transcript.md",
    WorkflowStage.VISUAL: "workflow/30-visual.md",
    WorkflowStage.DELIVERY: "workflow/40-delivery.md",
}


def next_stage(stage: WorkflowStage) -> WorkflowStage | None:
    index = ORDER.index(stage)
    if index + 1 >= len(ORDER):
        return None
    return ORDER[index + 1]


def rule_file(stage: WorkflowStage) -> str | None:
    """Return the one stage capsule an Agent should load for this task state."""
    return RULE_FILES.get(stage)
