from pathlib import Path

from agent_videonote.workflow.stages import ORDER, RULE_FILES, WorkflowStage, rule_file


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_prompt_files_stay_bounded() -> None:
    agents = ROOT / "AGENTS.md"
    core = ROOT / "workflow" / "00-core.md"
    stage_files = [ROOT / path for path in RULE_FILES.values()]

    assert agents.stat().st_size <= 2_500
    assert core.stat().st_size <= 2_000
    for path in stage_files:
        assert path.stat().st_size <= 3_000

    largest_path = max(stage_files, key=lambda path: path.stat().st_size)
    default_static_budget = (
        agents.stat().st_size + core.stat().st_size + largest_path.stat().st_size
    )
    assert default_static_budget <= 7_000


def test_every_active_stage_has_exactly_one_existing_rule_file() -> None:
    active = set(ORDER) - {WorkflowStage.DONE}
    assert set(RULE_FILES) == active
    assert rule_file(WorkflowStage.DONE) is None

    for stage, relative in RULE_FILES.items():
        assert relative.startswith("workflow/")
        assert (ROOT / relative).is_file(), stage


def test_stage_capsules_do_not_chain_or_pull_maintenance_docs() -> None:
    names = {Path(path).name for path in RULE_FILES.values()}
    for relative in RULE_FILES.values():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "docs/" not in text
        for other in names - {Path(relative).name}:
            assert other not in text


def test_agents_routes_from_machine_summary_instead_of_hardcoded_stage_map() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "workflow_file" in text
    for fragment in (
        "input → `workflow/10-input.md`",
        "transcript → `workflow/20-transcript.md`",
        "visual → `workflow/30-visual.md`",
        "delivery → `workflow/40-delivery.md`",
    ):
        assert fragment not in text
