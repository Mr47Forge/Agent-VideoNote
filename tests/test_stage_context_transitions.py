from pathlib import Path

from agent_videonote.adapters.mcp.facade import McpToolFacade
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
        raise AssertionError("not used")

    def cut_audio(self, source, output, *, start, duration, speed=1.0):
        raise AssertionError("not used")

    def extract_frame(self, source, output, *, second):
        raise AssertionError("not used")


def _facade(tmp_path: Path) -> McpToolFacade:
    root = tmp_path / "data"
    paths = RuntimePaths(
        root=root,
        tasks=root / "tasks",
        models=root / "models",
        context=root / "context",
        backups=root / "backups",
    )
    store = JsonTaskStore(paths.tasks)
    app = ApplicationService(
        config=RuntimeConfig(paths=paths),
        tasks=TaskService(store),
        workflow=WorkflowEngine(store),
        media=FakeMedia(),
        asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    return McpToolFacade(app)


def test_stage_advancing_tools_return_the_next_context_key(tmp_path: Path) -> None:
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

    facade = _facade(tmp_path)

    prepared = facade.prepare(str(source))
    task_id = prepared["task"]["task_id"]
    assert prepared["task"]["current_stage"] == "transcript"
    assert prepared["task"]["context_key"].startswith("transcript:")

    ingested = facade.ingest_srt(task_id, str(srt))
    assert ingested["task"]["current_stage"] == "visual"
    assert ingested["task"]["context_key"].startswith("visual:")

    visual_done = facade.complete_visual(task_id, {"checked": True})
    assert visual_done["task"]["current_stage"] == "delivery"
    assert visual_done["task"]["context_key"].startswith("delivery:")

    delivered = facade.validate_delivery(task_id, str(delivery))
    assert delivered["ok"] is True
    assert delivered["task"]["current_stage"] == "done"
    assert delivered["task"]["context_key"].startswith("done:")
