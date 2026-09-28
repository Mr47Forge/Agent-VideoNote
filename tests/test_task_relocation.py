from pathlib import Path

from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService


def test_same_content_at_new_path_resumes_same_task(tmp_path: Path) -> None:
    first_path = tmp_path / "D-drive" / "video.mp4"
    second_path = tmp_path / "E-drive" / "video.mp4"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    payload = (b"same-video-content-" * 1000)
    first_path.write_bytes(payload)
    second_path.write_bytes(payload)

    service = TaskService(JsonTaskStore(tmp_path / "tasks"))
    first = service.create_or_resume(first_path)
    second = service.create_or_resume(second_path)

    assert first.task_id == second.task_id
    assert second.source.path == str(second_path.resolve())
    assert any(event.type == "source.relocated_or_metadata_changed" for event in second.events)
