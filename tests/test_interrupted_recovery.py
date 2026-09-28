from pathlib import Path

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.core.types import Artifact
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.artifacts import write_json_atomic
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.transcripts.types import Transcript, TranscriptSegment
from agent_videonote.workflow.engine import WorkflowEngine


class FakeMedia:
    def probe(self, source):
        return MediaInfo(path=str(source), duration=10.0, format_name="fake", streams=())

    def extract_audio(self, source, output):
        raise AssertionError("recovery path must not rerun audio extraction")

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
    store = JsonTaskStore(paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    return ApplicationService(
        config=RuntimeConfig(paths=paths),
        tasks=tasks,
        workflow=workflow,
        media=FakeMedia(),
        asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )


def test_prepare_recovers_when_media_artifact_exists_but_stage_did_not_advance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)

    state = app.tasks.create_or_resume(source)
    media_path = write_json_atomic(
        app.task_dir(state.task_id) / "source" / "media.json",
        {"path": str(source), "duration": 10.0, "format_name": "fake", "streams": []},
    )
    app.tasks.register_artifact(
        state.task_id,
        "media_info",
        Artifact(kind="media_info", path=str(media_path)),
    )

    result = app.prepare(source)

    assert result["task"]["current_stage"] == "transcript"
    assert "input" in result["task"]["completed_stages"]


def test_transcribe_recovers_existing_transcript_without_provider_or_rerun(
    tmp_path: Path,
) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)
    task_id = app.prepare(source)["task"]["task_id"]

    transcript = Transcript(
        text="测试。",
        segments=(TranscriptSegment(start=0.0, end=1.0, text="测试。"),),
        source_id="test:recovery",
        language="zh",
    )
    path = write_json_atomic(
        app.task_dir(task_id) / "transcript" / "transcript.json",
        transcript.to_dict(),
    )
    app.tasks.register_artifact(
        task_id,
        "transcript",
        Artifact(kind="transcript", path=str(path), metadata={"source_id": transcript.source_id}),
    )

    summary = app.transcribe(task_id)

    assert summary["source_id"] == "test:recovery"
    state = app.tasks.get(task_id)
    assert state.current_stage == "visual"
    assert "transcript" in state.completed_stages


def test_delivery_recovers_done_stage_not_yet_marked_complete(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    srt = tmp_path / "video.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n测试。\n",
        encoding="utf-8",
    )
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    (delivery / "转写全文.md").write_text("测试。\n", encoding="utf-8")

    app = _app(tmp_path)
    task_id = app.prepare(source)["task"]["task_id"]
    app.ingest_srt(task_id, srt)
    app.complete_visual(task_id, {"checked": True})

    # Simulate a crash after DELIVERY -> DONE but before mark_done().
    app.workflow.complete_current(task_id, evidence={"delivery_report": "simulated"})
    interrupted = app.tasks.get(task_id)
    assert interrupted.current_stage == "done"
    assert "done" not in interrupted.completed_stages

    report = app.validate_and_finish_delivery(task_id, delivery)

    assert report.ok is True
    recovered = app.tasks.get(task_id)
    assert recovered.current_stage == "done"
    assert "done" in recovered.completed_stages


def test_prepare_adopts_orphan_media_file_without_reprobing(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)

    state = app.tasks.create_or_resume(source)
    orphan = write_json_atomic(
        app.task_dir(state.task_id) / "source" / "media.json",
        {"path": str(source), "duration": 10.0, "format_name": "fake", "streams": []},
    )

    result = app.prepare(source)

    assert result["task"]["current_stage"] == "transcript"
    recovered = app.tasks.get(state.task_id)
    assert recovered.artifacts["media_info"]["path"] == str(orphan)


def test_transcribe_adopts_orphan_transcript_without_provider_rerun(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)
    task_id = app.prepare(source)["task"]["task_id"]

    transcript = Transcript(
        text="孤儿转写。",
        segments=(TranscriptSegment(start=0.0, end=1.0, text="孤儿转写。"),),
        source_id="test:orphan",
        language="zh",
    )
    orphan = write_json_atomic(
        app.task_dir(task_id) / "transcript" / "transcript.json",
        transcript.to_dict(),
    )

    summary = app.transcribe(task_id)

    assert summary["source_id"] == "test:orphan"
    recovered = app.tasks.get(task_id)
    assert recovered.current_stage == "visual"
    assert recovered.artifacts["transcript"]["path"] == str(orphan)

