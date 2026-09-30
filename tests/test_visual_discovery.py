import json
from pathlib import Path

import pytest

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
from agent_videonote.storage.artifacts import read_json
from agent_videonote.visuals.discovery.scene import (
    DISCOVERY_ALGORITHM_VERSION, PROGRESS_SCHEMA_VERSION,
    DiscoveryConfig, FrameSample, SceneContentDiscovery, read_candidates,
)


def frame(low: int, high: int) -> bytes:
    return bytes((high if (x // 10) % 2 else low)
                 for y in range(90) for x in range(160))


A = frame(25, 220)
B = frame(220, 25)
C = bytes(245 if (x // 10 + y // 10) % 2 else 45
          for y in range(90) for x in range(160))
BRIGHT_A = frame(45, 245)
D = bytes((245 if value == 25 else 45) if 40 <= index % 160 < 70 else value
          for index, value in enumerate(A))
BLACK = bytes(160 * 90)


def narrow_page(*, changed: bool = False) -> bytes:
    """Text-like marks occupy a narrow column surrounded by blank margins."""
    pixels = bytearray([235] * (160 * 90))
    for y in range(8, 82):
        for x in range(57, 103):
            if y % 5 in (0, 1, 2) and x % 7 < 5:
                pixels[y * 160 + x] = 45
            if changed and 25 <= y < 70 and y % 4 in (0, 1, 2) and x % 5 < 4:
                pixels[y * 160 + x] = 20
    return bytes(pixels)


def shifted_zoom(pixels: bytes) -> bytes:
    result = bytearray(len(pixels))
    for y in range(90):
        for x in range(160):
            source_x = min(159, max(0, round((x - 80) / 1.04 + 80)))
            source_y = min(89, max(0, round((y - 45) / 1.04 + 45)))
            result[y * 160 + x] = pixels[source_y * 160 + source_x]
    return bytes(result)


class FakeSampler:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.starts: list[float] = []

    def sample(self, source, start, duration, interval):
        self.starts.append(start)
        return [FrameSample(float(i * 2), self.frames[i])
                for i in range(int(start / 2), min(len(self.frames), int((start + duration) / 2)))]


class FakeMedia:
    def __init__(self) -> None:
        self.extracted: list[float] = []

    def extract_frame(self, source, output, *, second):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"real source frame")
        self.extracted.append(second)
        return path


def run(tmp_path, frames, *, config=None, budget=120, sampler=None, media=None):
    sampler = sampler or FakeSampler(frames)
    media = media or FakeMedia()
    scanner = SceneContentDiscovery(media, sampler, config or DiscoveryConfig())
    result = scanner.scan(source=tmp_path / "source.mp4", fingerprint="source-v1",
                          duration=len(frames) * 2, visual_dir=tmp_path / "visual",
                          budget_seconds=budget)
    return result, sampler, media


def test_scene_change_selects_later_stable_frame(tmp_path):
    result, _, _ = run(tmp_path, [A, A, A, B, B, B])
    items = read_candidates(Path(result["artifact_path"]), start=0, limit=20)["candidates"]
    assert [item["timestamp"] for item in items] == [4.0, 10.0]
    assert items[1]["reason"] == "scene_change"
    assert items[1]["source_frame"]["detected_at"] == 6.0
    assert items[1]["change_score"] > 0.18
    assert all(Path(item["image_path"]).is_file() for item in items)


def test_gradual_content_change_without_scene_cut(tmp_path):
    result, _, _ = run(tmp_path, [A, A, A, D, D, D, D, D],
                       config=DiscoveryConfig(min_candidate_gap=2))
    items = read_candidates(Path(result["artifact_path"]), start=0, limit=20)["candidates"]
    assert [item["reason"] for item in items] == ["initial_stable_content", "content_change"]
    assert items[1]["timestamp"] == 12.0


def test_similar_candidate_is_deduplicated(tmp_path):
    config = DiscoveryConfig(scene_threshold=0.10, similarity_threshold=0.15)
    result, _, _ = run(tmp_path, [A, A, A] + [BRIGHT_A] * 5, config=config)
    assert result["raw_candidate_count"] == 2
    assert result["candidate_count"] == 1
    assert result["deduplicated_count"] == 1
    assert len(list((tmp_path / "visual" / "candidates").glob("*.jpg"))) == 1


def test_min_gap_and_max_candidates(tmp_path):
    frames = [A, A, A, B, B, B]
    gap, _, _ = run(tmp_path / "gap", frames, config=DiscoveryConfig(min_candidate_gap=8))
    cap, _, _ = run(tmp_path / "cap", frames, config=DiscoveryConfig(max_candidates=1))
    assert gap["candidate_count"] == 1
    assert cap["candidate_count"] == 1
    assert cap["raw_candidate_count"] == 2


def test_hourly_candidate_cap(tmp_path):
    result, _, _ = run(tmp_path, [A, A, A, B, B, B],
                       config=DiscoveryConfig(max_candidates_per_hour=1))
    assert result["candidate_count"] == 1
    assert result["raw_candidate_count"] == 2


def test_black_frames_are_filtered(tmp_path):
    result, _, _ = run(tmp_path, [BLACK, BLACK, BLACK, A, A, A])
    items = read_candidates(Path(result["artifact_path"]), start=0, limit=20)["candidates"]
    assert len(items) == 1
    assert items[0]["timestamp"] == 10.0
    assert result["filtered_count"] >= 3


def test_restart_resumes_at_checkpoint_and_reuses_candidates(tmp_path):
    frames = [A, A, A, A, A, B, B, B, B, B]
    config = DiscoveryConfig(chunk_seconds=10)
    sampler = FakeSampler(frames)
    media = FakeMedia()
    first, _, _ = run(tmp_path, frames, config=config, budget=10,
                      sampler=sampler, media=media)
    assert first["scanned_duration"] == 10
    assert not first["complete"]
    before = read_json(first["artifact_path"])["candidates"]
    assert read_json(first["artifact_path"])["schema_version"] == PROGRESS_SCHEMA_VERSION
    assert read_json(first["artifact_path"])["algorithm_version"] == DISCOVERY_ALGORITHM_VERSION
    second, _, _ = run(tmp_path, frames, config=config, budget=10,
                       sampler=sampler, media=media)
    assert second["complete"]
    assert sampler.starts == [0.0, 10.0]
    assert read_json(second["artifact_path"])["candidates"][:len(before)] == before
    third, _, _ = run(tmp_path, frames, config=config, budget=10,
                      sampler=sampler, media=media)
    assert third["candidate_count"] == second["candidate_count"]
    assert sampler.starts == [0.0, 10.0]


@pytest.mark.parametrize(("schema_version", "algorithm_version", "complete"), [
    (1, None, False),
    (1, None, True),
    (2, "incompatible-algorithm", False),
])
def test_old_progress_requires_new_scan_without_touching_artifacts(
        tmp_path, schema_version, algorithm_version, complete):
    frames = [A, A, A, B, B, B]
    sampler = FakeSampler(frames)
    media = FakeMedia()
    first, _, _ = run(tmp_path, frames, budget=120 if complete else 10,
                      sampler=sampler, media=media)
    manifest = Path(first["artifact_path"])
    progress = read_json(manifest)
    progress["schema_version"] = schema_version
    if algorithm_version is None:
        progress.pop("algorithm_version", None)
    else:
        progress["algorithm_version"] = algorithm_version
    manifest.write_text(json.dumps(progress), encoding="utf-8")
    manifest_before = manifest.read_bytes()
    images_before = {path: path.read_bytes()
                     for path in (tmp_path / "visual" / "candidates").glob("*.jpg")}
    starts_before = list(sampler.starts)

    with pytest.raises(ValueError, match="Start a new Visual Discovery v2 scan"):
        run(tmp_path, frames, budget=10, sampler=sampler, media=media)

    assert manifest.read_bytes() == manifest_before
    assert {path: path.read_bytes() for path in images_before} == images_before
    assert sampler.starts == starts_before


@pytest.mark.parametrize("complete", [False, True])
def test_unmarked_v2_progress_remains_resumable(tmp_path, complete):
    frames = [A, A, A, B, B, B]
    sampler = FakeSampler(frames)
    first, _, _ = run(tmp_path, frames, budget=120 if complete else 10,
                      sampler=sampler)
    manifest = Path(first["artifact_path"])
    progress = read_json(manifest)
    progress.pop("algorithm_version")
    manifest.write_text(json.dumps(progress), encoding="utf-8")
    starts_before = list(sampler.starts)

    result, _, _ = run(tmp_path, frames, budget=10, sampler=sampler)

    assert result["complete"]
    assert result["candidate_count"] == 2
    assert sampler.starts == (starts_before if complete else starts_before + [10.0])


def test_candidate_page_is_bounded(tmp_path):
    result, _, _ = run(tmp_path, [A, A, A])
    with pytest.raises(ValueError):
        read_candidates(Path(result["artifact_path"]), start=0, limit=51)


def test_narrow_local_text_change_below_global_threshold_is_found(tmp_path):
    original = narrow_page()
    changed = narrow_page(changed=True)
    result, _, _ = run(tmp_path, [original] * 4 + [changed] * 5,
                       config=DiscoveryConfig(min_candidate_gap=2))
    items = read_candidates(Path(result["artifact_path"]), start=0, limit=20)["candidates"]
    assert len(items) == 2
    assert items[1]["reason"] == "local_content_change"
    assert items[1]["global_change_score"] < 0.075
    assert items[1]["local_change_score"] > items[1]["global_change_score"]
    assert 0 < items[1]["changed_region_fraction"] < 0.5
    assert "perceptual" in items[1]["similarity"]


def test_nonadjacent_repeat_is_deduplicated_across_restart(tmp_path):
    frames = [A] * 3 + [B] * 3 + [C] * 3 + [A] * 3
    sampler = FakeSampler(frames)
    first, _, _ = run(tmp_path, frames, budget=18, sampler=sampler)
    assert first["scanned_duration"] == 18
    second, _, _ = run(tmp_path, frames, budget=18, sampler=sampler)
    items = read_candidates(Path(second["artifact_path"]), start=0, limit=20)["candidates"]
    assert second["raw_candidate_count"] == 4
    assert second["candidate_count"] == 3
    assert second["deduplicated_count"] == 1
    assert [item["timestamp"] for item in items] == [4.0, 10.0, 16.0]
    assert sampler.starts == [0.0, 18.0]
    assert all(item["fingerprint"] for item in read_json(second["artifact_path"])["candidates"])


def test_small_zoom_does_not_create_many_candidates(tmp_path):
    zoomed = shifted_zoom(A)
    result, _, _ = run(tmp_path, [A] * 3 + [zoomed] * 12,
                       config=DiscoveryConfig(min_candidate_gap=2))
    assert result["candidate_count"] == 1
    assert result["raw_candidate_count"] == 2
    assert result["deduplicated_count"] == 1


def test_application_discovery_preserves_transcript_and_task_stage(tmp_path, monkeypatch):
    import agent_videonote.application.visual_ops as visual_ops

    class AppMedia(FakeMedia):
        def probe(self, source):
            return MediaInfo(path=str(source), duration=12.0, format_name="fake", streams=())

    root = tmp_path / "data"
    paths = RuntimePaths(root=root, tasks=root / "tasks", models=root / "models",
                         context=root / "context", backups=root / "backups")
    store = JsonTaskStore(paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    app = ApplicationService(
        config=RuntimeConfig(paths=paths), tasks=tasks, workflow=workflow,
        media=AppMedia(), asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    task_id = app.prepare(source)["task"]["task_id"]
    transcript_path = app.task_dir(task_id) / "transcript" / "transcript.json"
    transcript_path.parent.mkdir(parents=True)
    transcript_path.write_bytes(b'{"text":"keep"}')
    tasks.register_artifact(task_id, "transcript", Artifact(kind="transcript", path=str(transcript_path)))
    workflow.complete_current(task_id, evidence={"transcript": str(transcript_path)})
    monkeypatch.setattr(visual_ops, "FFmpegFrameSampler",
                        lambda _bin: FakeSampler([A, A, A, B, B, B]))

    result = app.discover_visuals(task_id)

    assert result["complete"]
    assert tasks.get(task_id).current_stage == "visual"
    assert tasks.get(task_id).completed_stages == ["input", "transcript"]
    assert transcript_path.read_bytes() == b'{"text":"keep"}'
    assert tasks.get(task_id).artifacts["visual_discovery"]["path"] == result["artifact_path"]
