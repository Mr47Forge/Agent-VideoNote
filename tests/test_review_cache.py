from pathlib import Path

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.request import RecognitionContext
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.transcripts.types import Transcript, TranscriptSegment
from agent_videonote.workflow.engine import WorkflowEngine


class FakeMedia:
    def __init__(self):
        self.cut_calls = 0

    def probe(self, source):
        return MediaInfo(path=str(source), duration=10.0, format_name="fake", streams=())

    def extract_audio(self, source, output):
        raise AssertionError("not used")

    def cut_audio(self, source, output, *, start, duration, speed=1.0):
        self.cut_calls += 1
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return path

    def extract_frame(self, source, output, *, second):
        raise AssertionError("not used")


class FakeProvider:
    capabilities = frozenset(
        {
            AsrCapability.SHORT_AUDIO,
            AsrCapability.HOTWORDS,
            AsrCapability.FREE_CONTEXT,
            AsrCapability.EXPLICIT_LANGUAGE,
        }
    )

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self.calls = 0

    def transcribe(self, request):
        self.calls += 1
        source_range = request.source_range
        assert source_range is not None
        text = f"{self.provider_id}:{','.join(request.context.hotwords)}"
        return Transcript(
            text=text,
            segments=(
                TranscriptSegment(
                    start=source_range.start,
                    end=source_range.end,
                    text=text,
                ),
            ),
            source_id=f"fake:{self.provider_id}",
            language=request.context.language,
        )

    def close(self) -> None:
        pass


def _app(tmp_path: Path):
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
    media = FakeMedia()
    registry = ProviderRegistry()
    first = FakeProvider("review-a")
    second = FakeProvider("review-b")
    registry.register(first)
    registry.register(second)

    app = ApplicationService(
        config=RuntimeConfig(paths=paths),
        tasks=tasks,
        workflow=workflow,
        media=media,
        asr_registry=registry,
        asr_profile=AsrProfile(roles={"primary": None, "review": "review-a"}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    return app, media, first, second


def test_review_reuses_cache_for_identical_provider_and_context(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app, media, first, _ = _app(tmp_path)
    task_id = app.tasks.create_or_resume(source).task_id
    context = RecognitionContext(language="zh", hotwords=("术语",))

    first_result = app.review(task_id, start=1.0, end=3.0, context=context)
    second_result = app.review(task_id, start=1.0, end=3.0, context=context)

    assert first_result == second_result
    assert first.calls == 1
    assert media.cut_calls == 1


def test_review_context_change_does_not_reuse_old_cache(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app, media, first, _ = _app(tmp_path)
    task_id = app.tasks.create_or_resume(source).task_id

    app.review(
        task_id,
        start=1.0,
        end=3.0,
        context=RecognitionContext(hotwords=("旧词",)),
    )
    app.review(
        task_id,
        start=1.0,
        end=3.0,
        context=RecognitionContext(hotwords=("新词",)),
    )

    assert first.calls == 2
    assert media.cut_calls == 2


def test_review_provider_change_does_not_reuse_old_cache(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    app, _, first, second = _app(tmp_path)
    task_id = app.tasks.create_or_resume(source).task_id
    context = RecognitionContext(hotwords=("术语",))

    app.review(task_id, start=1.0, end=3.0, context=context)
    app.asr_profile = AsrProfile(roles={"primary": None, "review": "review-b"})
    result = app.review(task_id, start=1.0, end=3.0, context=context)

    assert first.calls == 1
    assert second.calls == 1
    assert result["source_id"] == "fake:review-b"
