import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.models import TaskState
from agent_videonote.tasks.service import TaskService
from agent_videonote.core.types import SourceIdentity


def _state(tmp_path: Path) -> tuple[JsonTaskStore, str]:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    identity = SourceIdentity.from_path(source)
    task_id = "a" * 16
    store = JsonTaskStore(tmp_path / "tasks")
    store.create(TaskState.new(task_id, identity, "input"))
    return store, task_id


def test_two_store_instances_do_not_lose_concurrent_mutations(tmp_path: Path) -> None:
    store_a, task_id = _state(tmp_path)
    store_b = JsonTaskStore(tmp_path / "tasks")

    def mutate(index: int) -> None:
        store = store_a if index % 2 == 0 else store_b

        def change(state: TaskState) -> None:
            state.add_event("concurrency.test", {"index": index})

        store.mutate(task_id, change)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(mutate, range(40)))

    state = store_a.load(task_id)
    seen = {
        event.detail["index"]
        for event in state.events
        if event.type == "concurrency.test"
    }
    assert seen == set(range(40))


def test_stale_short_lock_is_recovered(tmp_path: Path) -> None:
    store, task_id = _state(tmp_path)
    lock_path = store.task_dir(task_id) / ".state.lock"
    lock_path.write_text("stale\n", encoding="utf-8")
    old = time.time() - 60
    os.utime(lock_path, (old, old))

    def change(state: TaskState) -> None:
        state.add_event("after-stale-lock", {})

    state = store.mutate(task_id, change)

    assert any(event.type == "after-stale-lock" for event in state.events)
    assert not lock_path.exists()


def test_unresolved_upsert_is_atomic_across_service_instances(tmp_path: Path) -> None:
    store_a, task_id = _state(tmp_path)
    store_b = JsonTaskStore(tmp_path / "tasks")
    service_a = TaskService(store_a)
    service_b = TaskService(store_b)

    def add(index: int) -> None:
        service = service_a if index % 2 == 0 else service_b
        service.add_unresolved(
            task_id,
            "visual_cleanup",
            {"candidate_id": "vc-0001", "reason": "needs-review"},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(40)))

    state = store_a.load(task_id)
    matching = [
        item for item in state.unresolved
        if item.get("category") == "visual_cleanup"
        and item.get("candidate_id") == "vc-0001"
    ]
    assert matching == [{
        "category": "visual_cleanup",
        "candidate_id": "vc-0001",
        "reason": "needs-review",
    }]
