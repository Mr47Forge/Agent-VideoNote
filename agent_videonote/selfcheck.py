from __future__ import annotations

import tempfile
from pathlib import Path

from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.transcripts.srt import load_srt
from agent_videonote.workflow.engine import WorkflowEngine


def run_selfcheck() -> list[str]:
    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="agent-videonote-") as temp:
        root = Path(temp)
        source = root / "sample.mp4"
        source.write_bytes(b"sample")

        store = JsonTaskStore(root / "tasks")
        tasks = TaskService(store)
        workflow = WorkflowEngine(store)

        first = tasks.create_or_resume(source)
        second = tasks.create_or_resume(source)
        if first.task_id != second.task_id:
            raise RuntimeError("task resume identity check failed")
        checks.append("task-resume")

        workflow.complete_current(first.task_id, evidence={"selfcheck": True})
        reloaded = tasks.get(first.task_id)
        if reloaded.current_stage != "transcript":
            raise RuntimeError("workflow persistence check failed")
        checks.append("workflow-persistence")

        srt = root / "sample.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n测试。\n",
            encoding="utf-8",
        )
        transcript = load_srt(srt)
        if len(transcript.segments) != 1 or transcript.source_id != "subtitle:srt":
            raise RuntimeError("SRT normalization check failed")
        checks.append("srt-normalization")

    return checks


def main() -> None:
    checks = run_selfcheck()
    print("Agent-VideoNote selfcheck OK: " + ", ".join(checks))


if __name__ == "__main__":
    main()
