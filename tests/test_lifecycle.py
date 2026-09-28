from pathlib import Path

from agent_videonote.lifecycle.inspector import inspect_task_storage
from agent_videonote.lifecycle.planner import plan_safe_cleanup


def test_storage_report_is_bounded_and_grouped(tmp_path: Path) -> None:
    task = tmp_path / "task"
    (task / "temp").mkdir(parents=True)
    (task / "transcript").mkdir()
    (task / "temp" / "a.bin").write_bytes(b"a" * 10)
    (task / "transcript" / "transcript.json").write_bytes(b"b" * 20)
    (task / "state.json").write_bytes(b"c" * 5)

    report = inspect_task_storage(task)

    assert report.total_files == 3
    assert report.total_bytes == 35
    assert report.truncated is False
    usage = {item.name: (item.files, item.bytes) for item in report.areas}
    assert usage["temp"] == (1, 10)
    assert usage["transcript"] == (1, 20)
    assert usage["root"] == (1, 5)


def test_cleanup_plan_only_contains_safe_reproducible_intermediates(tmp_path: Path) -> None:
    task = tmp_path / "task"
    temp = task / "temp"
    review_audio = task / "reviews" / "audio"
    review_results = task / "reviews" / "results"
    transcript = task / "transcript"
    delivery = task / "delivery"
    for directory in (temp, review_audio, review_results, transcript, delivery):
        directory.mkdir(parents=True, exist_ok=True)

    (temp / "scratch.bin").write_bytes(b"x" * 11)
    (review_audio / "done.wav").write_bytes(b"a" * 12)
    (review_results / "done.json").write_text("{}", encoding="utf-8")
    (review_audio / "unresolved.wav").write_bytes(b"u" * 13)
    (transcript / "transcript.json").write_text("{}", encoding="utf-8")
    (delivery / "report.json").write_text("{}", encoding="utf-8")
    (task / "state.json.dead.tmp").write_bytes(b"t" * 14)

    plan = plan_safe_cleanup("a" * 16, task)
    by_name = {Path(item.path).name: item.reason for item in plan.candidates}

    assert by_name["scratch.bin"] == "task-temp"
    assert by_name["done.wav"] == "review-audio-has-persisted-result"
    assert by_name["state.json.dead.tmp"] == "orphan-atomic-temp"
    assert "unresolved.wav" not in by_name
    assert "transcript.json" not in by_name
    assert "report.json" not in by_name
    assert plan.total_files == 3
    assert plan.total_bytes == 37


def test_storage_report_stops_at_file_limit(tmp_path: Path) -> None:
    task = tmp_path / "task"
    temp = task / "temp"
    temp.mkdir(parents=True)
    for index in range(10):
        (temp / f"{index}.bin").write_bytes(b"x")

    report = inspect_task_storage(task, max_files=4)

    assert report.total_files == 4
    assert report.truncated is True
