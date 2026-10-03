from pathlib import Path

from agent_videonote.workflow.context import build_workflow_context, workflow_context_key
from agent_videonote.workflow.stages import ORDER, RULE_RESOURCES, WorkflowStage


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "agent_videonote" / "workflow" / "rules"


def test_runtime_prompt_files_stay_bounded() -> None:
    agents = ROOT / "AGENTS.md"
    core = RULES / "00-core.md"
    stage_files = [RULES / name for name in RULE_RESOURCES.values()]

    assert agents.stat().st_size <= 2_500
    assert core.stat().st_size <= 2_000
    for path in stage_files:
        assert path.stat().st_size <= 3_000

    largest_path = max(stage_files, key=lambda path: path.stat().st_size)
    runtime_budget = core.stat().st_size + largest_path.stat().st_size
    assert runtime_budget <= 5_000


def test_every_active_stage_has_exactly_one_packaged_rule() -> None:
    active = set(ORDER) - {WorkflowStage.DONE}
    assert set(RULE_RESOURCES) == active

    for stage, name in RULE_RESOURCES.items():
        assert "/" not in name
        assert (RULES / name).is_file(), stage


def test_stage_capsules_are_independent_of_maintenance_docs() -> None:
    names = set(RULE_RESOURCES.values())
    for name in names:
        text = (RULES / name).read_text(encoding="utf-8")
        assert "docs/" not in text
        for other in names - {name}:
            assert other not in text


def test_context_key_changes_with_stage_and_context_is_bounded() -> None:
    keys = {workflow_context_key(stage) for stage in ORDER}
    assert len(keys) == len(ORDER)

    for stage in ORDER:
        context = build_workflow_context(stage)
        assert context["stage"] == stage.value
        assert context["context_key"] == workflow_context_key(stage)
        assert len(context["core_rules"].encode("utf-8")) <= 2_000
        if stage == WorkflowStage.DONE:
            assert context["stage_rules"] is None
        else:
            assert len(context["stage_rules"].encode("utf-8")) <= 3_000


def test_agents_uses_mcp_context_not_repo_workflow_paths() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "task_context" in text
    assert "context_key" in text
    assert "workflow/00-core.md" not in text
