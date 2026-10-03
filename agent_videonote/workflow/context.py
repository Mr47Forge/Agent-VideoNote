from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agent_videonote.workflow.stages import RULE_RESOURCES, WorkflowStage


_RULES_DIR = Path(__file__).with_name("rules")
_CORE_RESOURCE = "00-core.md"


def _read_rule(name: str) -> str:
    path = _RULES_DIR / name
    if not path.is_file():
        raise RuntimeError(f"packaged workflow rule is missing: {name}")
    return path.read_text(encoding="utf-8").strip()


def workflow_context_key(stage: WorkflowStage) -> str:
    core = _read_rule(_CORE_RESOURCE)
    stage_text = _read_rule(RULE_RESOURCES[stage]) if stage in RULE_RESOURCES else ""
    digest = hashlib.sha256(
        (stage.value + "\0" + core + "\0" + stage_text).encode("utf-8")
    ).hexdigest()[:16]
    return f"{stage.value}:{digest}"


def build_workflow_context(stage: WorkflowStage) -> dict[str, Any]:
    """Build one bounded, host-independent runtime capsule for the current stage."""
    stage_resource = RULE_RESOURCES.get(stage)
    stage_rules = _read_rule(stage_resource) if stage_resource else None
    return {
        "schema_version": 1,
        "stage": stage.value,
        "context_key": workflow_context_key(stage),
        "core_rules": _read_rule(_CORE_RESOURCE),
        "stage_rules": stage_rules,
    }
