from pathlib import Path

from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.workflow.engine import WorkflowEngine


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
