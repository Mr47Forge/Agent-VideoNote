from pathlib import Path

import pytest

from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.workflow.engine import WorkflowEngine
from agent_videonote.workflow.stages import WorkflowStage


def test_completed_stage_survives_reload(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)

    state = tasks.create_or_resume(source)
    workflow.complete_current(state.task_id, evidence={"ok": True})

    reloaded = store.load(state.task_id)
    assert "input" in reloaded.completed_stages
    assert reloaded.current_stage == "transcript"


def test_expected_stage_completion_is_idempotent_not_double_advance(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    state = tasks.create_or_resume(source)

    first = workflow.complete_current(
        state.task_id,
        evidence={"worker": 1},
        expected_stage=WorkflowStage.INPUT,
    )
    assert first.current_stage == "transcript"

    stale = workflow.complete_current(
        state.task_id,
        evidence={"worker": 2},
        expected_stage=WorkflowStage.INPUT,
    )
    assert stale.current_stage == "transcript"
    assert stale.completed_stages == ["input"]


def test_expected_stage_rejects_unrelated_stale_completion(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    state = tasks.create_or_resume(source)

    with pytest.raises(InvalidTransitionError, match="stale workflow completion"):
        workflow.complete_current(
            state.task_id,
            expected_stage=WorkflowStage.VISUAL,
        )


def test_mark_done_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    state = tasks.create_or_resume(source)

    for stage in (
        WorkflowStage.INPUT,
        WorkflowStage.TRANSCRIPT,
        WorkflowStage.VISUAL,
        WorkflowStage.DELIVERY,
    ):
        workflow.complete_current(
            state.task_id,
            expected_stage=stage,
        )

    first = workflow.mark_done(state.task_id, evidence={"worker": 1})
    second = workflow.mark_done(state.task_id, evidence={"worker": 2})

    assert first.completed_stages.count("done") == 1
    assert second.completed_stages.count("done") == 1
    done_events = [event for event in second.events if event.type == "workflow.done"]
    assert len(done_events) == 1
