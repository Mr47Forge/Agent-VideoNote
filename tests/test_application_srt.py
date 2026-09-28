from pathlib import Path

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.workflow.engine import WorkflowEngine


class FakeMedia:
    def probe(self, source):
        return MediaInfo(path=str(source), duration=10.0, format_name="fake", streams=())

    def extract_audio(self, source, output):
        raise AssertionError("SRT path must not run ASR audio extraction")

    def cut_audio(self, source, output, *, start, duration, speed=1.0):
        raise AssertionError("not used")

    def extract_frame(self, source, output, *, second):
        raise AssertionError("not used")


def _app(tmp_path: Path) -> ApplicationService:
    root = tmp_path / "data"
    paths = RuntimePaths(
        root=root,
        tasks=root / "tasks",
        models=root / "models",
        context=root / "context",
        backups=root / "backups",
    )
    config = RuntimeConfig(paths=paths)
    store = JsonTaskStore(paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    return ApplicationService(
        config=config,
        tasks=tasks,
        workflow=workflow,
        media=FakeMedia(),
        asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )


def test_srt_ingest_returns_summary_and_transcript_is_sliced(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    srt = tmp_path / "video.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n第一句。\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n第二句。\n",
        encoding="utf-8",
    )

    app = _app(tmp_path)
    prepared = app.prepare(source)
    task_id = prepared["task"]["task_id"]

    summary = app.ingest_srt(task_id, srt)
    assert "text" not in summary
    assert summary["segments"] == 2
    assert summary["read_with"] == "get_transcript"

    page = app.get_transcript(task_id, start_segment=1, end_segment=1)
    assert page["total"] == 2
    assert page["has_more"] is True
    assert page["segments"][0]["text"] == "第一句。"
    assert "words" not in page["segments"][0]
