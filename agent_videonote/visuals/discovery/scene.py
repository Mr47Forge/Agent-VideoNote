from __future__ import annotations

import base64
import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from agent_videonote.storage.artifacts import read_json, write_json_atomic


_WIDTH = 64
_HEIGHT = 36
_FRAME_BYTES = _WIDTH * _HEIGHT


@dataclass(frozen=True)
class DiscoveryConfig:
    sampling_interval: float = 2.0
    scene_threshold: float = 0.18
    content_threshold: float = 0.075
    stability_threshold: float = 0.055
    stability_window: int = 2
    similarity_threshold: float = 0.045
    min_candidate_gap: float = 6.0
    max_candidates: int = 120
    max_candidates_per_hour: int = 100
    chunk_seconds: float = 60.0
    min_brightness: float = 0.04
    min_detail: float = 0.015
    min_active_fraction: float = 0.08

    def __post_init__(self) -> None:
        if not 0.5 <= self.sampling_interval <= 10:
            raise ValueError("sampling_interval must be between 0.5 and 10 seconds")
        for name in ("scene_threshold", "content_threshold", "stability_threshold",
                     "similarity_threshold", "min_brightness", "min_detail",
                     "min_active_fraction"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.stability_window not in (1, 2, 3):
            raise ValueError("stability_window must be 1, 2, or 3")
        if not 0 <= self.min_candidate_gap <= 60:
            raise ValueError("min_candidate_gap must be between 0 and 60 seconds")
        if not 1 <= self.max_candidates <= 500:
            raise ValueError("max_candidates must be between 1 and 500")
        if not 1 <= self.max_candidates_per_hour <= 120:
            raise ValueError("max_candidates_per_hour must be between 1 and 120")
        if not 10 <= self.chunk_seconds <= 120:
            raise ValueError("chunk_seconds must be between 10 and 120 seconds")


@dataclass(frozen=True)
class FrameSample:
    second: float
    pixels: bytes


class FrameSampler(Protocol):
    def sample(self, source: Path, start: float, duration: float,
               interval: float) -> list[FrameSample]: ...


class FFmpegFrameSampler:
    """Decode only bounded grayscale thumbnails; never persist intermediate frames."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self.ffmpeg_bin = ffmpeg_bin

    def sample(self, source: Path, start: float, duration: float,
               interval: float) -> list[FrameSample]:
        count = math.ceil(duration / interval)
        args = [self.ffmpeg_bin, "-hide_banner", "-loglevel", "error",
                "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
                "-i", str(source), "-an", "-sn",
                "-vf", f"fps=1/{interval:.6f},scale={_WIDTH}:{_HEIGHT}:flags=area,format=gray",
                "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        try:
            result = subprocess.run(args, capture_output=True, check=True,
                                    timeout=max(90, duration * 4))
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"visual sampling failed: {exc.stderr.decode('utf-8', 'replace')[-600:]}") from exc
        if len(result.stdout) % _FRAME_BYTES:
            raise RuntimeError("visual sampling returned an incomplete frame")
        return [FrameSample(round(start + i * interval, 3),
                            result.stdout[i * _FRAME_BYTES:(i + 1) * _FRAME_BYTES])
                for i in range(min(count, len(result.stdout) // _FRAME_BYTES))]


def _difference(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / (_FRAME_BYTES * 255)


def _quality(pixels: bytes) -> tuple[float, float, float]:
    brightness = sum(pixels) / (_FRAME_BYTES * 255)
    detail = sum(abs(pixels[i] - pixels[i - 1]) for i in range(1, _FRAME_BYTES)) / ((_FRAME_BYTES - 1) * 255)
    active_fraction = sum(pixel > 24 for pixel in pixels) / _FRAME_BYTES
    return brightness, detail, active_fraction


def _encode(pixels: bytes | None) -> str | None:
    return base64.b64encode(pixels).decode("ascii") if pixels is not None else None


def _decode(value: str | None) -> bytes | None:
    return base64.b64decode(value) if value else None


class SceneContentDiscovery:
    """Incremental scene/content discovery with an atomic checkpoint per chunk."""

    def __init__(self, media, sampler: FrameSampler,
                 config: DiscoveryConfig | None = None) -> None:
        self.media = media
        self.sampler = sampler
        self.config = config or DiscoveryConfig()

    def scan(self, *, source: Path, fingerprint: str, duration: float,
             visual_dir: Path, budget_seconds: float = 120.0) -> dict:
        if not 2 <= budget_seconds <= 600:
            raise ValueError("budget_seconds must be between 2 and 600")
        if duration <= 0 or not math.isfinite(duration):
            raise ValueError("positive finite video duration is required")
        manifest_path = visual_dir / "discovery" / "progress.json"
        image_dir = visual_dir / "candidates"
        if manifest_path.is_file():
            progress = read_json(manifest_path)
            if (progress.get("source_fingerprint") != fingerprint
                    or progress.get("config") != asdict(self.config)):
                raise ValueError("visual discovery source or configuration changed; existing progress was preserved")
        else:
            progress = {
                "schema_version": 1, "source_fingerprint": fingerprint,
                "source_path": str(source), "duration": duration,
                "config": asdict(self.config), "scanned_until": 0.0,
                "raw_candidate_count": 0, "deduplicated_count": 0,
                "filtered_count": 0, "candidates": [],
                "previous_frame": None, "reference_frame": None,
                "pending": None, "complete": False,
            }
        stop = min(duration, progress["scanned_until"] + budget_seconds)
        while progress["scanned_until"] < stop - 0.001:
            start = progress["scanned_until"]
            end = min(stop, start + self.config.chunk_seconds)
            samples = self.sampler.sample(source, start, end - start,
                                          self.config.sampling_interval)
            for sample in samples:
                self._observe(progress, sample, source, image_dir)
            progress["scanned_until"] = round(end, 3)
            progress["complete"] = end >= duration - 0.001
            write_json_atomic(manifest_path, progress)
            self._prune_superseded(image_dir, progress)
        self._prune_superseded(image_dir, progress)
        return self.summary(progress, manifest_path)

    def _observe(self, progress: dict, sample: FrameSample,
                 source: Path, image_dir: Path) -> None:
        frame = sample.pixels
        if len(frame) != _FRAME_BYTES:
            raise ValueError("invalid thumbnail dimensions")
        previous = _decode(progress["previous_frame"])
        reference = _decode(progress["reference_frame"])
        delta = _difference(previous, frame) if previous else 0.0
        baseline_delta = _difference(reference, frame) if reference else 0.0
        brightness, detail, active_fraction = _quality(frame)
        valid = (brightness >= self.config.min_brightness
                 and detail >= self.config.min_detail
                 and active_fraction >= self.config.min_active_fraction)
        pending = progress["pending"]

        if not valid:
            progress["filtered_count"] += 1
            progress["pending"] = None
        elif previous is None:
            progress["pending"] = {"reason": "initial_stable_content", "score": 0.0,
                                   "detected_at": sample.second, "stable": 0}
        elif delta >= self.config.scene_threshold:
            progress["pending"] = {"reason": "scene_change", "score": round(delta, 4),
                                   "detected_at": sample.second, "stable": 0}
        elif pending is not None:
            if delta <= self.config.stability_threshold:
                pending["stable"] += 1
                if pending["stable"] >= self.config.stability_window:
                    self._accept(progress, sample, source, image_dir, pending,
                                 brightness, detail, active_fraction)
                    progress["pending"] = None
                    progress["reference_frame"] = _encode(frame)
            else:
                pending["stable"] = 0
        elif (reference is not None and baseline_delta >= self.config.content_threshold
              and delta <= self.config.stability_threshold):
            self._accept(progress, sample, source, image_dir,
                         {"reason": "content_change", "score": round(baseline_delta, 4),
                          "detected_at": sample.second, "stable": 1}, brightness, detail,
                         active_fraction)
            progress["reference_frame"] = _encode(frame)
        progress["previous_frame"] = _encode(frame)

    def _accept(self, progress: dict, sample: FrameSample, source: Path,
                image_dir: Path, pending: dict, brightness: float, detail: float,
                active_fraction: float) -> None:
        progress["raw_candidate_count"] += 1
        candidates = progress["candidates"]
        last = candidates[-1] if candidates else None
        similarity = _difference(_decode(last["thumbnail"]), sample.pixels) if last else None
        if similarity is not None and similarity <= self.config.similarity_threshold:
            progress["deduplicated_count"] += 1
            if detail <= last["stability"]["detail"]:
                return
            candidate_id = last["candidate_id"]
            replaced = True
        else:
            replaced = False
            if last and sample.second - last["timestamp"] < self.config.min_candidate_gap:
                progress["filtered_count"] += 1
                return
            if len(candidates) >= self.config.max_candidates:
                progress["filtered_count"] += 1
                return
            hour_count = sum(int(c["timestamp"] // 3600) == int(sample.second // 3600)
                             for c in candidates)
            if hour_count >= self.config.max_candidates_per_hour:
                progress["filtered_count"] += 1
                return
            candidate_id = f"vc-{len(candidates) + 1:04d}"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"{candidate_id}-{sample.second:.3f}.jpg"
        self.media.extract_frame(source, image_path, second=sample.second)
        item = {
            "candidate_id": candidate_id, "timestamp": sample.second,
            "image_path": str(image_path), "reason": pending["reason"],
            "change_score": pending["score"],
            "stability": {"samples": pending["stable"], "brightness": round(brightness, 4),
                          "detail": round(detail, 4),
                          "active_fraction": round(active_fraction, 4)},
            "similarity": {"difference_from_previous": round(similarity, 4) if similarity is not None else None,
                           "deduplicated": replaced},
            "source_frame": {"video": str(source), "timestamp": sample.second,
                             "detected_at": pending["detected_at"],
                             "sampling_interval": self.config.sampling_interval},
            "thumbnail": _encode(sample.pixels),
        }
        if replaced:
            candidates[-1] = item
        else:
            candidates.append(item)

    @staticmethod
    def _prune_superseded(image_dir: Path, progress: dict) -> None:
        if not image_dir.is_dir():
            return
        kept = {Path(item["image_path"]) for item in progress["candidates"]}
        for path in image_dir.glob("vc-*.jpg"):
            if path not in kept:
                path.unlink(missing_ok=True)

    @staticmethod
    def summary(progress: dict, manifest_path: Path) -> dict:
        return {
            "scanned_duration": progress["scanned_until"],
            "total_duration": progress["duration"],
            "raw_candidate_count": progress["raw_candidate_count"],
            "candidate_count": len(progress["candidates"]),
            "deduplicated_count": progress["deduplicated_count"],
            "filtered_count": progress["filtered_count"],
            "complete": progress["complete"],
            "progress": round(progress["scanned_until"] / progress["duration"], 4),
            "artifact_path": str(manifest_path),
        }


def read_candidates(manifest_path: Path, *, start: int, limit: int) -> dict:
    if start < 0 or not 1 <= limit <= 50:
        raise ValueError("start must be nonnegative and limit must be between 1 and 50")
    progress = read_json(manifest_path)
    page = [{key: value for key, value in item.items() if key != "thumbnail"}
            for item in progress["candidates"][start:start + limit]]
    return {"total": len(progress["candidates"]), "start": start,
            "limit": limit, "candidates": page,
            "scanned_duration": progress["scanned_until"], "complete": progress["complete"]}
