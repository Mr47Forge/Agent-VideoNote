from pathlib import Path

from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService


def test_create_or_resume_is_stable(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    service = TaskService(store)

    first = service.create_or_resume(source)
    second = service.create_or_resume(source)

    assert first.task_id == second.task_id
    assert first.created_at == second.created_at
    assert (tmp_path / "tasks" / first.task_id / "state.json").is_file()
