import json
from pathlib import Path

from agent_videonote.core.errors import StateSchemaError
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

def test_unsupported_task_schema_fails_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    store = JsonTaskStore(tmp_path / "tasks")
    service = TaskService(store)
    state = service.create_or_resume(source)

    state_path = store.state_path(state.task_id)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        service.get(state.task_id)
    except StateSchemaError as exc:
        assert "unsupported task state schema" in str(exc)
    else:
        raise AssertionError("unsupported schema must fail explicitly")

