from pathlib import Path

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.core.types import Artifact
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.workflow.engine import WorkflowEngine


class FakeMedia:
    def probe(self, source):
        return MediaInfo(path=str(source), duration=1.0, format_name="fake", streams=())

    def extract_audio(self, source, output):
        raise AssertionError("not used")

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
    return ApplicationService(
        config=RuntimeConfig(paths=paths),
        tasks=TaskService(store),
        workflow=WorkflowEngine(store),
        media=FakeMedia(),
        asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )


def test_task_summary_stays_bounded_when_many_review_artifacts_exist(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)
    task_id = app.tasks.create_or_resume(source).task_id

    transcript = tmp_path / "transcript.json"
    transcript.write_text("{}", encoding="utf-8")
    app.tasks.register_artifact(
        task_id,
        "transcript",
        Artifact(kind="transcript", path=str(transcript)),
    )

    for index in range(150):
        review = tmp_path / f"review-{index}.json"
        review.write_text("{}", encoding="utf-8")
        app.tasks.register_artifact(
            task_id,
            f"review:{index}",
            Artifact(
                kind="asr_review",
                path=str(review),
                metadata={"large": "x" * 1000},
            ),
        )

    result = app.get_task(task_id)

    assert "artifacts" not in result
    assert result["artifact_total"] == 151
    assert result["artifact_counts"]["asr_review"] == 150
    assert result["artifact_counts"]["transcript"] == 1
    assert set(result["core_artifacts"]) == {"transcript"}
    assert "review:0" not in str(result)

def test_task_summary_exposes_machine_routed_workflow_and_bounded_unresolved_counts(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)
    state = app.tasks.create_or_resume(source)
    app.tasks.add_unresolved(state.task_id, "visual_cleanup", {"candidate_id": "vc-0001"})
    app.tasks.add_unresolved(state.task_id, "visual_cleanup", {"candidate_id": "vc-0002"})
    app.tasks.add_unresolved(state.task_id, "asr_review", {"start": 1.0, "end": 2.0})

    result = app.get_task(state.task_id)

    assert result["context_key"].startswith("input:")
    assert result["context_tool"] == "task_context"
    assert result["unresolved_count"] == 3
    assert result["unresolved_counts"] == {"visual_cleanup": 2, "asr_review": 1}
    assert "candidate_id" not in str(result["unresolved_counts"])


def test_task_context_combines_bounded_state_and_current_stage_rules(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app = _app(tmp_path)
    state = app.tasks.create_or_resume(source)

    result = app.get_task_context(state.task_id)

    assert result["task"]["task_id"] == state.task_id
    assert result["workflow"]["stage"] == "input"
    assert result["workflow"]["context_key"] == result["task"]["context_key"]
    assert "源内容忠实优先" in result["workflow"]["core_rules"]
    assert "确认源视频身份" in result["workflow"]["stage_rules"]
