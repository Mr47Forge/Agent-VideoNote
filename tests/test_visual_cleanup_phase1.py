import json
from pathlib import Path

import pytest

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.context.repository import CourseContextRepository
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.core.errors import InvalidTransitionError
from agent_videonote.core.types import Artifact, SourceIdentity
from agent_videonote.media.types import MediaInfo
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.storage.json_store import JsonTaskStore
from agent_videonote.tasks.service import TaskService
from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.types import CleanupResult
from agent_videonote.visuals.cleanup.source_search import (
    SourceFrameCleanup, SourceSearchConfig, select_clean_frame,
)
from agent_videonote.visuals.discovery.features import encode, fingerprints, preview
from agent_videonote.visuals.discovery.scene import FrameSample
from agent_videonote.workflow.engine import WorkflowEngine


def page(*, added_text=False):
    pixels = bytearray([220] * (160 * 90))
    for y in range(12, 87):
        for x in range(20, 140):
            if y % 7 in (0, 1) and x % 11 < 8:
                pixels[y * 160 + x] = 35
            if added_text and 35 <= y < 56 and 60 <= x < 125:
                if y % 4 in (0, 1) and x % 6 < 4:
                    pixels[y * 160 + x] = 20
    return bytes(pixels)


def overlay(pixels):
    result = bytearray(pixels)
    for y in range(74, 88):
        for x in range(10, 150):
            result[y * 160 + x] = 4
    return bytes(result)


class FakeSampler:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []
        self.counts = []

    def sample(self, source, start, duration, interval):
        self.calls.append((start, duration, interval))
        result = [FrameSample(float(second), self.frames[second])
                  for second in sorted(self.frames)
                  if start <= second < start + duration]
        self.counts.append(len(result))
        return result


class FakeMedia:
    def __init__(self, frames):
        self.frames = frames
        self.extracted = []

    def probe(self, source):
        return MediaInfo(path=str(source), duration=11.0, format_name="fake", streams=())

    def extract_frame(self, source, output, *, second):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.frames[int(second)])
        self.extracted.append(second)
        return path


def candidate(frame, image_path, *, second=5.0):
    return {
        "candidate_id": "vc-0001", "timestamp": second,
        "image_path": str(image_path),
        "fingerprint": {"hashes": fingerprints(frame),
                        "preview": encode(preview(frame))},
        "source_frame": {"video": "", "timestamp": second},
    }


def clean_direct(tmp_path, frames):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")
    original = tmp_path / "candidate.jpg"
    original.write_bytes(frames[5])
    media = FakeMedia(frames)
    sampler = FakeSampler(frames)
    cleaner = SourceFrameCleanup(media, sampler, build_default_cleanup_registry())
    result = cleaner.clean(
        source=source, candidate=candidate(frames[5], original), duration=11,
        temp_dir=tmp_path / "temp", output_path=tmp_path / "clean.jpg",
    )
    return result, media, sampler


def test_transient_overlay_is_replaced_with_real_clean_frame(tmp_path):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    result, media, sampler = clean_direct(tmp_path, frames)
    assert result.resolved
    assert result.strategy_id == "source-frame-replacement"
    assert result.detail["replacement_timestamp"] in (0, 1, 2, 3, 4, 6, 7, 8, 9, 10)
    assert Path(result.output_path).read_bytes() == clean
    assert len(sampler.calls) == 1
    assert sum(sampler.counts) <= 16
    assert not list((tmp_path / "temp").glob("*.jpg"))
    assert len(media.extracted) == 1


def test_changed_page_cannot_replace_candidate(tmp_path):
    first = page()
    second = bytes(255 - value for value in first)
    frames = {index: first if index <= 5 else second for index in range(11)}
    result, media, _ = clean_direct(tmp_path, frames)
    assert result.status == "clean"
    assert result.detail["evidence"]["search_reason"] == "no_two_sided_same_state_witness"
    assert not media.extracted


def test_changed_chat_text_is_not_treated_as_disappearing_ad(tmp_path):
    original = page()
    with_text = page(added_text=True)
    frames = {second: with_text if second == 5 else original for second in range(11)}
    result, media, _ = clean_direct(tmp_path, frames)
    assert result.status == "clean"
    assert not media.extracted


def test_changed_chat_bubble_is_not_treated_as_opaque_overlay(tmp_path):
    original = page()
    changed = bytearray(original)
    for y in range(35, 55):
        for x in range(45, 125):
            changed[y * 160 + x] = 100
            if y % 5 in (0, 1) and x % 7 < 5:
                changed[y * 160 + x] = 240
    frames = {second: bytes(changed) if second == 5 else original
              for second in range(11)}
    result, media, _ = clean_direct(tmp_path, frames)
    assert result.status == "clean"
    assert not media.extracted


def test_no_clean_frame_without_overlay_evidence_is_clean(tmp_path):
    covered = overlay(page())
    frames = {second: covered for second in range(11)}
    result, media, _ = clean_direct(tmp_path, frames)
    assert result.status == "clean"
    assert result.detail["evidence"]["search_reason"] == "no_verified_clean_frame"
    assert not media.extracted


def test_verified_overlay_with_unavailable_strategy_is_unresolved(tmp_path):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    source = tmp_path / "video.mp4"
    source.write_bytes(b"source")
    image = tmp_path / "candidate.jpg"
    image.write_bytes(frames[5])
    result = SourceFrameCleanup(FakeMedia(frames), FakeSampler(frames), CleanupRegistry()).clean(
        source=source, candidate=candidate(frames[5], image), duration=11,
        temp_dir=tmp_path / "temp", output_path=tmp_path / "clean.jpg",
    )
    assert result.status == "unresolved"
    assert result.detail["unresolved_reason"] == "replacement_strategy_rejected"
    assert result.detail["evidence"]["occluded_pixel_fraction"] > 0


def test_prefers_more_complete_stable_witness():
    clearer = page()
    softened = bytearray(clearer)
    for y in range(12, 32):
        for x in range(21, 139):
            index = y * 160 + x
            softened[index] = (clearer[index - 1] + clearer[index] + clearer[index + 1]) // 3
    dirty = overlay(clearer)
    nearby = [FrameSample(3.0, bytes(softened)), FrameSample(7.0, clearer)]
    result, _ = select_clean_frame(FrameSample(5.0, dirty), nearby, SourceSearchConfig())
    assert result is not None
    assert result.timestamp == 7.0


def build_app(tmp_path, frames):
    root = tmp_path / "data"
    paths = RuntimePaths(root, root / "tasks", root / "models",
                         root / "context", root / "backups")
    store = JsonTaskStore(paths.tasks)
    tasks = TaskService(store)
    workflow = WorkflowEngine(store)
    media = FakeMedia(frames)
    app = ApplicationService(
        config=RuntimeConfig(paths), tasks=tasks, workflow=workflow,
        media=media, asr_registry=ProviderRegistry(),
        asr_profile=AsrProfile(roles={"primary": None, "review": None}),
        contexts=CourseContextRepository(paths.context / "courses"),
    )
    return app, media


def prepared_task(app, tmp_path, frames):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source video")
    task_id = app.prepare(source)["task"]["task_id"]
    transcript = app.task_dir(task_id) / "transcript" / "transcript.json"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b'{"text":"keep"}')
    app.tasks.register_artifact(task_id, "transcript",
                                Artifact(kind="transcript", path=str(transcript)))
    app.workflow.complete_current(task_id, evidence={"transcript": str(transcript)})
    image = app.task_dir(task_id) / "visual" / "candidates" / "vc-0001-5.000.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(frames[5])
    item = candidate(frames[5], image)
    item["source_frame"]["video"] = str(source.resolve())
    manifest = app.task_dir(task_id) / "visual" / "discovery" / "progress.json"
    write_json_atomic(manifest, {
        "source_path": str(source.resolve()),
        "source_fingerprint": SourceIdentity.from_path(source).fingerprint,
        "duration": 11, "scanned_until": 11.0,
        "candidates": [item], "complete": True,
    })
    app.tasks.register_artifact(task_id, "visual_discovery",
                                Artifact(kind="visual_discovery", path=str(manifest)))
    return task_id, image, manifest, transcript


def test_application_persists_result_and_reuses_it_after_restart(tmp_path, monkeypatch):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    app, media = build_app(tmp_path, frames)
    task_id, _, _, transcript = prepared_task(app, tmp_path, frames)
    sampler = FakeSampler(frames)
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: sampler)

    first = app.clean_visual_candidate(task_id, "vc-0001")
    assert first["resolved"]
    assert first["replacement_timestamp"] != first["original_timestamp"]
    assert Path(first["output_path"]).read_bytes() == clean
    assert transcript.read_bytes() == b'{"text":"keep"}'
    calls = list(sampler.calls)
    restarted, _ = build_app(tmp_path, frames)
    second = restarted.clean_visual_candidate(task_id, "vc-0001")
    assert second == first
    assert sampler.calls == calls
    assert len(media.extracted) == 1
    result_path = restarted.task_dir(task_id) / "visual" / "cleanup" / "vc-0001.json"
    assert read_json(result_path)["original_image_path"]
    assert restarted.tasks.get(task_id).artifacts["visual_cleanup"]["path"] == str(result_path.parent)


def test_clean_is_persistent_and_never_added_to_unresolved(tmp_path, monkeypatch):
    covered = overlay(page())
    frames = {second: covered for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    sampler = FakeSampler(frames)
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: sampler)
    first = app.clean_visual_candidate(task_id, "vc-0001")
    second = app.clean_visual_candidate(task_id, "vc-0001")
    assert first == second
    assert first["status"] == "clean"
    assert len(sampler.calls) == 1
    assert not [x for x in app.tasks.get(task_id).unresolved
                if x["category"] == "visual_cleanup"]


def test_evidenced_unresolved_is_persistent_and_not_duplicated(tmp_path, monkeypatch):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    app.cleanup_registry = CleanupRegistry()
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    sampler = FakeSampler(frames)
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: sampler)
    first = app.clean_visual_candidate(task_id, "vc-0001")
    second = app.clean_visual_candidate(task_id, "vc-0001")
    assert first == second
    assert first["status"] == "unresolved"
    assert first["unresolved_reason"] == "replacement_strategy_rejected"
    assert len(sampler.calls) == 1
    assert len([x for x in app.tasks.get(task_id).unresolved
                if x["category"] == "visual_cleanup"]) == 1


def test_legacy_unresolved_is_reassessed_and_only_matching_issue_removed(tmp_path, monkeypatch):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, image, _, _ = prepared_task(app, tmp_path, frames)
    result_path = app.task_dir(task_id) / "visual" / "cleanup" / "vc-0001.json"
    write_json_atomic(result_path, {
        "schema_version": 1, "candidate_id": "vc-0001",
        "source_fingerprint": SourceIdentity.from_path(tmp_path / "source.mp4").fingerprint,
        "original_timestamp": 5.0, "original_image_path": str(image.resolve()),
        "replacement_timestamp": None, "output_path": None,
        "strategy_id": "source-frame-replacement", "confidence": None,
        "evidence": {"sample_count": 12}, "resolved": False,
        "unresolved_reason": "no_verified_clean_frame",
    })
    app.tasks.add_unresolved(task_id, "visual_cleanup", {
        "candidate_id": "vc-0001", "reason": "no_verified_clean_frame"})
    app.tasks.add_unresolved(task_id, "asr_review", {"candidate_id": "vc-0001"})
    app.tasks.add_unresolved(task_id, "visual_cleanup", {"candidate_id": "vc-9999"})
    sampler = FakeSampler(frames)
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: sampler)
    first = app.clean_visual_candidate(task_id, "vc-0001")
    assert first["status"] == "clean"
    assert read_json(result_path)["schema_version"] == 2
    assert read_json(result_path.with_suffix(".phase1.json"))["schema_version"] == 1
    assert {(x["category"], x["candidate_id"]) for x in app.tasks.get(task_id).unresolved} == {
        ("asr_review", "vc-0001"), ("visual_cleanup", "vc-9999")}
    restarted, _ = build_app(tmp_path, frames)
    assert restarted.clean_visual_candidate(task_id, "vc-0001") == first
    assert len(sampler.calls) == 1


def test_legacy_resolved_result_is_reused_without_rescanning(tmp_path, monkeypatch):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, image, _, _ = prepared_task(app, tmp_path, frames)
    result_path = app.task_dir(task_id) / "visual" / "cleanup" / "vc-0001.json"
    output = app.task_dir(task_id) / "visual" / "cleaned" / "vc-0001.jpg"
    output.parent.mkdir(parents=True)
    output.write_bytes(clean)
    write_json_atomic(result_path, {
        "schema_version": 1, "candidate_id": "vc-0001",
        "source_fingerprint": SourceIdentity.from_path(tmp_path / "source.mp4").fingerprint,
        "original_timestamp": 5.0, "original_image_path": str(image.resolve()),
        "replacement_timestamp": 4.0, "output_path": str(output),
        "strategy_id": "source-frame-replacement", "confidence": 0.9,
        "evidence": {"occluded_pixel_fraction": 0.1}, "resolved": True,
        "unresolved_reason": None,
    })
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: pytest.fail("legacy resolved result must not be scanned"))
    summary = app.clean_visual_candidate(task_id, "vc-0001")
    assert summary["status"] == "resolved"
    assert summary["replacement_timestamp"] == 4.0
    assert read_json(result_path)["schema_version"] == 1
    assert not result_path.with_suffix(".phase1.json").exists()


def test_candidate_must_belong_to_current_task_and_source(tmp_path, monkeypatch):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, image, manifest, _ = prepared_task(app, tmp_path, frames)
    monkeypatch.setattr("agent_videonote.application.visual_ops.FFmpegFrameSampler",
                        lambda _bin: FakeSampler(frames))
    other = tmp_path / "other.jpg"
    other.write_bytes(image.read_bytes())
    progress = read_json(manifest)
    progress["candidates"][0]["image_path"] = str(other)
    write_json_atomic(manifest, progress)
    with pytest.raises(ValueError, match="provenance"):
        app.clean_visual_candidate(task_id, "vc-0001")
    progress["candidates"][0]["image_path"] = str(image)
    progress["source_fingerprint"] = "wrong"
    write_json_atomic(manifest, progress)
    with pytest.raises(ValueError, match="source"):
        app.clean_visual_candidate(task_id, "vc-0001")


def test_search_config_rejects_unbounded_nearby_frames():
    with pytest.raises(ValueError, match="max_samples"):
        SourceSearchConfig(radius_seconds=6, sampling_interval=0.5, max_samples=20)


class FakeMaskedRepairStrategy:
    strategy_id = "fake-mask"

    def __init__(self):
        self.calls = []

    def capabilities(self):
        return {
            "strategy_id": self.strategy_id,
            "available": True,
            "kind": "image_inpaint",
            "requires_mask": True,
            "requires_gpu": False,
            "external_runtime": False,
            "automatic_text_removal": False,
        }

    def preflight(self):
        return []

    def can_handle(self, request):
        return (
            request.hints.get("provider") == self.strategy_id
            and bool(request.hints.get("mask_path"))
        )

    def clean(self, request):
        self.calls.append(request)
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(Path(request.image_path).read_bytes())
        return CleanupResult(
            status="resolved",
            output_path=str(output),
            strategy_id=self.strategy_id,
            detail={"generated_pixels": True},
        )


class FakeTemporalMaskedRepairStrategy(FakeMaskedRepairStrategy):
    strategy_id = "vsr-sttn"


class FakeGpuMaskedRepairStrategy(FakeMaskedRepairStrategy):
    strategy_id = "fake-gpu"

    def capabilities(self):
        result = super().capabilities()
        result["strategy_id"] = self.strategy_id
        result["may_use_gpu"] = True
        return result


def test_explicit_masked_repair_is_persisted_and_idempotent(tmp_path):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, image, _, _ = prepared_task(app, tmp_path, frames)
    mask = tmp_path / "manual-mask.png"
    mask.write_bytes(b"explicit mask")

    registry = CleanupRegistry()
    strategy = FakeMaskedRepairStrategy()
    registry.register(strategy)
    app.cleanup_registry = registry

    first = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="fake-mask",
        mask_path=str(mask),
    )
    second = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="fake-mask",
        mask_path=str(mask),
    )

    assert first == second
    assert first["status"] == "resolved"
    assert first["provider"] == "fake-mask"
    assert Path(first["output_path"]).read_bytes() == image.read_bytes()
    assert len(strategy.calls) == 1
    assert app.tasks.get(task_id).artifacts["visual_repairs"]["path"].endswith(
        str(Path("visual") / "repairs")
    )


def test_explicit_masked_repair_rejects_unknown_provider(tmp_path):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    mask = tmp_path / "manual-mask.png"
    mask.write_bytes(b"explicit mask")

    with pytest.raises(ValueError, match="cannot be used"):
        app.repair_visual_candidate(
            task_id,
            "vc-0001",
            provider="unknown-provider",
            mask_path=str(mask),
        )


def test_batch_cleanup_reduces_agent_round_trips_and_reuses_persisted_results(
        tmp_path, monkeypatch):
    clean = page()
    frames = {second: overlay(clean) if second == 5 else clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    sampler = FakeSampler(frames)
    monkeypatch.setattr(
        "agent_videonote.application.visual_ops.FFmpegFrameSampler",
        lambda _bin: sampler,
    )

    first = app.clean_visual_candidates(task_id, start=0, limit=20)

    assert first["processed"] == 1
    assert first["has_more"] is False
    assert first["counts"] == {"clean": 0, "resolved": 1, "unresolved": 0}
    assert first["reused_count"] == 0
    assert len(first["resolved"]) == 1
    assert first["unresolved"] == []
    assert len(sampler.calls) == 1

    second = app.clean_visual_candidates(task_id, start=0, limit=20)

    assert second["processed"] == 1
    assert second["reused_count"] == 1
    assert len(sampler.calls) == 1


def test_masked_repair_variants_use_distinct_persistent_outputs(tmp_path):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    mask_a = tmp_path / "mask-a.png"
    mask_b = tmp_path / "mask-b.png"
    mask_a.write_bytes(b"mask-a")
    mask_b.write_bytes(b"mask-b")

    registry = CleanupRegistry()
    strategy = FakeMaskedRepairStrategy()
    registry.register(strategy)
    app.cleanup_registry = registry

    first = app.repair_visual_candidate(
        task_id, "vc-0001", provider="fake-mask", mask_path=str(mask_a)
    )
    second = app.repair_visual_candidate(
        task_id, "vc-0001", provider="fake-mask", mask_path=str(mask_b)
    )

    assert first["request_key"] != second["request_key"]
    assert first["output_path"] != second["output_path"]
    assert Path(first["output_path"]).is_file()
    assert Path(second["output_path"]).is_file()
    assert len(strategy.calls) == 2


def test_temporal_repair_cache_key_includes_window_and_interval(tmp_path):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")

    registry = CleanupRegistry()
    strategy = FakeTemporalMaskedRepairStrategy()
    registry.register(strategy)
    app.cleanup_registry = registry

    first = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="vsr-sttn",
        mask_path=str(mask),
        window_seconds=2.0,
        interval=1.0,
    )
    second = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="vsr-sttn",
        mask_path=str(mask),
        window_seconds=3.0,
        interval=1.0,
    )
    repeated = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="vsr-sttn",
        mask_path=str(mask),
        window_seconds=3.0,
        interval=1.0,
    )

    assert first["request_key"] != second["request_key"]
    assert first["output_path"] != second["output_path"]
    assert second == repeated
    assert len(strategy.calls) == 2


def test_cleanup_and_repair_wait_for_discovery_completion(tmp_path, monkeypatch):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, manifest, _ = prepared_task(app, tmp_path, frames)
    progress = read_json(manifest)
    progress["complete"] = False
    write_json_atomic(manifest, progress)
    monkeypatch.setattr(
        "agent_videonote.application.visual_ops.FFmpegFrameSampler",
        lambda _bin: FakeSampler(frames),
    )

    with pytest.raises(InvalidTransitionError, match="discovery must complete"):
        app.clean_visual_candidates(task_id)
    with pytest.raises(InvalidTransitionError, match="discovery must complete"):
        app.clean_visual_candidate(task_id, "vc-0001")

    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    registry = CleanupRegistry()
    registry.register(FakeMaskedRepairStrategy())
    app.cleanup_registry = registry
    with pytest.raises(InvalidTransitionError, match="discovery must complete"):
        app.repair_visual_candidate(
            task_id,
            "vc-0001",
            provider="fake-mask",
            mask_path=str(mask),
        )


def test_gpu_visual_repair_releases_resident_asr_provider_first(tmp_path):
    clean = page()
    frames = {second: clean for second in range(11)}
    app, _ = build_app(tmp_path, frames)
    task_id, _, _, _ = prepared_task(app, tmp_path, frames)
    mask = tmp_path / "mask-gpu.png"
    mask.write_bytes(b"mask")

    class ResidentGpuProvider:
        provider_id = "resident-review"
        capabilities = frozenset({AsrCapability.GPU})

        def __init__(self):
            self.is_loaded = True
            self.closes = 0

        def close(self):
            self.is_loaded = False
            self.closes += 1

    resident = ResidentGpuProvider()
    app.asr_registry.register(resident)

    registry = CleanupRegistry()
    strategy = FakeGpuMaskedRepairStrategy()
    registry.register(strategy)
    app.cleanup_registry = registry

    result = app.repair_visual_candidate(
        task_id,
        "vc-0001",
        provider="fake-gpu",
        mask_path=str(mask),
    )

    assert result["resolved"] is True
    assert resident.closes == 1
    assert app.asr_registry.loaded_providers() == []
    assert len(strategy.calls) == 1
