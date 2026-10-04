from pathlib import Path

import pytest

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.request import TranscriptionRequest
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.transcripts.types import Transcript, TranscriptSegment
from agent_videonote.workflow.engine import WorkflowEngine


class FakeGpuProvider:
    capabilities = frozenset({
        AsrCapability.GPU, AsrCapability.SHORT_AUDIO,
        AsrCapability.LONG_AUDIO, AsrCapability.SEGMENT_TIMESTAMPS,
    })

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self.is_loaded = False
        self.loads = 0
        self.calls = 0
        self.closes = 0

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        if not self.is_loaded:
            self.loads += 1
            self.is_loaded = True
        self.calls += 1
        start = request.source_range.start if request.source_range else 0.0
        end = request.source_range.end if request.source_range else 2.0
        return Transcript(
            text="test", segments=(TranscriptSegment(start=start, end=end, text="test"),),
            source_id=f"asr:{self.provider_id}",
        )

    def close(self) -> None:
        self.is_loaded = False
        self.closes += 1


class FailingGpuProvider(FakeGpuProvider):
    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        class Model:
            pass
        self.model = Model()
        self.is_loaded = True
        self.loads += 1
        self.calls += 1
        model = self.model  # Mimic provider and upstream inference frame locals.
        assert model is self.model
        raise RuntimeError("simulated ASR failure")

    def close(self) -> None:
        import gc
        import weakref
        reference = weakref.ref(self.model)
        self.model = None
        gc.collect()
        assert reference() is None, "traceback retained model during release"
        super().close()


class FakeMedia:
    def probe(self, source):
        return MediaInfo(path=str(source), duration=10.0, format_name="fake", streams=())

    def extract_audio(self, source, output):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return path

    def cut_audio(self, source, output, *, start, duration, speed=1.0):
        return self.extract_audio(source, output)


def _request(tmp_path: Path) -> TranscriptionRequest:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio")
    return TranscriptionRequest(path)


def test_gpu_registry_evicts_other_provider_and_release_is_idempotent(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    first = FakeGpuProvider("provider-a")
    second = FakeGpuProvider("provider-b")
    registry.register(first)
    registry.register(second)
    request = _request(tmp_path)

    registry.get("provider-a").transcribe(request)
    assert registry.loaded_providers() == [{"provider_id": "provider-a", "gpu": True}]
    registry.get("provider-b").transcribe(request)
    assert first.closes == 1
    assert registry.loaded_providers() == [{"provider_id": "provider-b", "gpu": True}]
    registry.get("provider-b").transcribe(request)
    assert second.loads == 1
    assert registry.release_provider("provider-b") is True
    assert registry.release_provider("provider-b") is False
    assert second.closes == 1
    registry.get("provider-a").transcribe(request)
    assert first.loads == 2
    assert set(registry.list_capabilities()) == {"provider-a", "provider-b"}


def test_primary_releases_after_persistence_review_reuses_until_stage_release(tmp_path: Path) -> None:
    paths = RuntimePaths(tmp_path / "data", tmp_path / "data" / "tasks", tmp_path / "data" / "models", tmp_path / "data" / "context", tmp_path / "data" / "backups")
    store = JsonTaskStore(paths.tasks)
    registry = ProviderRegistry()
    primary = FakeGpuProvider("provider-a")
    review = FakeGpuProvider("provider-b")
    registry.register(primary)
    registry.register(review)
    app = ApplicationService(
        config=RuntimeConfig(paths), tasks=TaskService(store), workflow=WorkflowEngine(store),
        media=FakeMedia(), asr_registry=registry,
        asr_profile=AsrProfile({"primary": "provider-a", "review": "provider-b"}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    task_id = app.prepare(source)["task"]["task_id"]

    summary = app.transcribe(task_id)
    assert summary["segments"] == 1
    assert summary["reused"] is False
    assert summary["elapsed_seconds"] >= 0
    assert Path(summary["path"]).is_file()
    assert summary["task"]["current_stage"] == "visual"
    assert summary["task"]["context_key"].startswith("visual:")
    assert app.get_task(task_id)["current_stage"] == "visual"
    assert primary.closes == 1
    assert app.loaded_providers() == []

    app.review(task_id, start=0, end=2)
    app.review(task_id, start=2, end=4)
    assert review.loads == 1
    assert review.calls == 2
    assert app.loaded_providers() == [{"provider_id": "provider-b", "gpu": True}]
    assert app.release_role("review")["released"] is True
    assert app.release_role("review")["released"] is False
    app.review(task_id, start=4, end=6)
    assert review.loads == 2
    assert primary.loads == 1


def test_primary_provider_is_released_when_transcription_fails(tmp_path: Path) -> None:
    paths = RuntimePaths(
        tmp_path / "data",
        tmp_path / "data" / "tasks",
        tmp_path / "data" / "models",
        tmp_path / "data" / "context",
        tmp_path / "data" / "backups",
    )
    store = JsonTaskStore(paths.tasks)
    registry = ProviderRegistry()
    primary = FailingGpuProvider("provider-a")
    registry.register(primary)
    app = ApplicationService(
        config=RuntimeConfig(paths),
        tasks=TaskService(store),
        workflow=WorkflowEngine(store),
        media=FakeMedia(),
        asr_registry=registry,
        asr_profile=AsrProfile({"primary": "provider-a", "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    task_id = app.prepare(source)["task"]["task_id"]

    with pytest.raises(RuntimeError, match="simulated ASR failure"):
        app.transcribe(task_id)

    assert primary.closes == 1
    assert app.loaded_providers() == []
    state = app.tasks.get(task_id)
    assert state.current_stage == "transcript"
    assert "transcript" not in state.artifacts
