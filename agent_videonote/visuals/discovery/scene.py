from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.visuals.discovery.features import (
    FRAME_BYTES, HEIGHT, PREVIEW_HEIGHT, PREVIEW_WIDTH, WIDTH,
    aligned_difference, change, decode, difference, encode, fingerprints,
    hash_distance, preview, wide_aligned_difference,
)


PROGRESS_SCHEMA_VERSION = 2
DISCOVERY_ALGORITHM_VERSION = "visual-discovery-v2"


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
    chunk_seconds: float = 300.0
    min_brightness: float = 0.04
    min_detail: float = 0.015
    min_active_fraction: float = 0.08
    local_content_threshold: float = 0.10
    local_peak_threshold: float = 0.15
    local_tile_threshold: float = 0.07
    perceptual_threshold: float = 0.15
    max_pending_seconds: float = 8.0
    min_persistent_gap: float = 30.0

    def __post_init__(self) -> None:
        if not 0.5 <= self.sampling_interval <= 10:
            raise ValueError("sampling_interval must be between 0.5 and 10 seconds")
        for name in ("scene_threshold", "content_threshold", "stability_threshold",
                     "similarity_threshold", "min_brightness", "min_detail",
                     "min_active_fraction", "local_content_threshold",
                     "local_peak_threshold", "local_tile_threshold",
                     "perceptual_threshold"):
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
        if not 10 <= self.chunk_seconds <= 600:
            raise ValueError("chunk_seconds must be between 10 and 600 seconds")
        if not 4 <= self.max_pending_seconds <= 20:
            raise ValueError("max_pending_seconds must be between 4 and 20 seconds")
        if not 10 <= self.min_persistent_gap <= 120:
            raise ValueError("min_persistent_gap must be between 10 and 120 seconds")


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
                "-vf", f"fps=1/{interval:.6f},scale={WIDTH}:{HEIGHT}:flags=area,format=gray",
                "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        try:
            result = subprocess.run(args, capture_output=True, check=True,
                                    timeout=max(90, duration * 4))
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"visual sampling failed: {exc.stderr.decode('utf-8', 'replace')[-600:]}") from exc
        if len(result.stdout) % FRAME_BYTES:
            raise RuntimeError("visual sampling returned an incomplete frame")
        actual = len(result.stdout) // FRAME_BYTES
        if actual != count:
            raise RuntimeError(
                f"visual sampling returned {actual} frames; expected {count} "
                f"for {duration:.3f}s at {interval:.3f}s interval"
            )
        # Label each frame at the center of its sampling bin. The last bin can
        # be shorter than interval, so its center must remain strictly before
        # the requested end instead of being labeled at video duration.
        samples: list[FrameSample] = []
        for i in range(count):
            bin_start = i * interval
            bin_end = min(duration, (i + 1) * interval)
            second = start + (bin_start + bin_end) / 2
            samples.append(
                FrameSample(
                    round(second, 3),
                    result.stdout[i * FRAME_BYTES:(i + 1) * FRAME_BYTES],
                )
            )
        return samples


def _quality(pixels: bytes) -> tuple[float, float, float]:
    brightness = sum(pixels) / (FRAME_BYTES * 255)
    # A three-pixel stride keeps the quality scale comparable to the old
    # 64-wide thumbnail after increasing detection resolution to 160 pixels.
    stride = 3
    detail = sum(abs(pixels[row + x] - pixels[row + x - stride])
                 for row in range(0, FRAME_BYTES, WIDTH)
                 for x in range(stride, WIDTH)) / (HEIGHT * (WIDTH - stride) * 255)
    active_fraction = sum(pixel > 24 for pixel in pixels) / FRAME_BYTES
    return brightness, detail, active_fraction


class SceneContentDiscovery:
    """Incremental scene/content discovery with an atomic checkpoint per chunk."""

    def __init__(self, media, sampler: FrameSampler,
                 config: DiscoveryConfig | None = None) -> None:
        self.media = media
        self.sampler = sampler
        self.config = config or DiscoveryConfig()

    def scan(self, *, source: Path, fingerprint: str, duration: float,
             visual_dir: Path, budget_seconds: float = 600.0) -> dict:
        if not 2 <= budget_seconds <= 3600:
            raise ValueError("budget_seconds must be between 2 and 3600")
        if duration <= 0 or not math.isfinite(duration):
            raise ValueError("positive finite video duration is required")
        manifest_path = visual_dir / "discovery" / "progress.json"
        image_dir = visual_dir / "candidates"
        if manifest_path.is_file():
            progress = read_json(manifest_path)
            # Early v2 checkpoints already use schema 2 but predate the
            # explicit algorithm marker. They use this same discovery logic.
            if (progress.get("schema_version") != PROGRESS_SCHEMA_VERSION
                    or progress.get("algorithm_version") not in
                    (None, DISCOVERY_ALGORITHM_VERSION)):
                raise ValueError(
                    "visual discovery progress belongs to an older or incompatible version; "
                    "existing progress and candidates were preserved. "
                    "Start a new Visual Discovery v2 scan in a new visual artifact directory."
                )
            if progress.get("source_fingerprint") != fingerprint:
                raise ValueError("visual discovery source or configuration changed; existing progress was preserved")
            current_config = asdict(self.config)
            previous_config = {key: value for key, value in current_config.items()
                               if key not in ("max_pending_seconds", "min_persistent_gap")}
            if progress.get("config") == previous_config:
                # Completed v2 artifacts remain readable. An unfinished v2
                # checkpoint lacks the persisted pending frame used by this
                # revision and must be rescanned in a new artifact directory.
                if progress.get("complete"):
                    return self.summary(progress, manifest_path)
                raise ValueError(
                    "visual discovery progress predates persistent-motion support; "
                    "existing progress and candidates were preserved. "
                    "Start a new Visual Discovery v2 scan in a new visual artifact directory."
                )
            if progress.get("config") != current_config:
                raise ValueError("visual discovery source or configuration changed; existing progress was preserved")
            if progress.get("complete"):
                self._prune_superseded(image_dir, progress)
                return self.summary(progress, manifest_path)
        else:
            progress = {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "algorithm_version": DISCOVERY_ALGORITHM_VERSION,
                "source_fingerprint": fingerprint,
                "source_path": str(source), "duration": duration,
                "config": asdict(self.config), "scanned_until": 0.0,
                "raw_candidate_count": 0, "deduplicated_count": 0,
                "filtered_count": 0, "candidates": [], "duplicate_events": [],
                "previous_frame": None, "reference_frame": None,
                "pending": None, "complete": False,
            }
        stop = min(duration, progress["scanned_until"] + budget_seconds)
        while progress["scanned_until"] < stop - 0.001:
            start = progress["scanned_until"]
            end = min(stop, start + self.config.chunk_seconds)
            samples = self.sampler.sample(
                source,
                start,
                end - start,
                self.config.sampling_interval,
            )
            expected_samples = math.ceil(
                (end - start) / self.config.sampling_interval
            )
            if len(samples) != expected_samples:
                raise RuntimeError(
                    f"visual sampling returned {len(samples)} frames for "
                    f"{start:.3f}-{end:.3f}; expected {expected_samples}; "
                    "checkpoint was not advanced"
                )
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
        if len(frame) != FRAME_BYTES:
            raise ValueError("invalid thumbnail dimensions")
        previous = decode(progress["previous_frame"])
        reference = decode(progress["reference_frame"])
        delta = difference(previous, frame) if previous else 0.0
        brightness, detail, active_fraction = _quality(frame)
        valid = (brightness >= self.config.min_brightness
                 and detail >= self.config.min_detail
                 and active_fraction >= self.config.min_active_fraction)
        pending = progress["pending"]

        def best_frame(adjacent_delta: float) -> dict:
            return {"timestamp": sample.second, "frame": encode(frame),
                    "brightness": brightness, "detail": detail,
                    "active_fraction": active_fraction, "adjacent_delta": adjacent_delta}

        def event(reason: str, measured, detected_at: float, stable: int) -> dict:
            return {
                "reason": reason,
                "score": round(measured.local_score if reason == "local_content_change"
                               else measured.global_score, 4),
                "global_score": round(measured.global_score, 4),
                "local_score": round(measured.local_score, 4),
                "changed_region_fraction": round(measured.changed_region_fraction, 4),
                "detected_at": detected_at, "stable": stable,
                "started_at": sample.second, "start_frame": encode(frame),
                "best_frame": best_frame(delta),
                "best_changed_frame": None,
            }

        if not valid:
            progress["filtered_count"] += 1
            progress["pending"] = None
        elif previous is None:
            progress["pending"] = {
                "reason": "initial_stable_content", "score": 0.0,
                "global_score": 0.0, "local_score": 0.0,
                "changed_region_fraction": 0.0,
                "detected_at": sample.second, "stable": 0,
                "started_at": sample.second, "start_frame": encode(frame),
                "best_frame": best_frame(delta),
                "best_changed_frame": None,
            }
        elif pending is not None:
            # A new scene score during continuous zoom/scroll must not restart
            # the clock indefinitely. Keep the clearest low-motion frame in a
            # bounded pending window, including across chunk checkpoints.
            pending.setdefault("started_at", pending["detected_at"])
            pending.setdefault("start_frame", encode(previous))
            prior_best = pending.get("best_frame")
            current_best = best_frame(delta)
            if (prior_best is None or
                    (detail - 0.08 * delta) >=
                    (prior_best["detail"] - 0.08 * prior_best["adjacent_delta"])):
                pending["best_frame"] = current_best
            anchor = reference or decode(pending["start_frame"])
            anchor_change = change(anchor, frame,
                                   active_threshold=self.config.local_tile_threshold)
            content_changed = (
                anchor_change.global_score >= self.config.content_threshold
                or (anchor_change.local_score >= self.config.local_content_threshold
                    and anchor_change.max_local_score >= self.config.local_peak_threshold
                    and anchor_change.largest_region >= 2))
            prior_changed = pending.get("best_changed_frame")
            if content_changed and (prior_changed is None or
                                    (detail - 0.08 * delta) >=
                                    (prior_changed["detail"] -
                                     0.08 * prior_changed["adjacent_delta"])):
                pending["best_changed_frame"] = current_best
            if delta <= self.config.stability_threshold:
                pending["stable"] += 1
                if pending["stable"] >= self.config.stability_window:
                    self._accept(progress, sample, source, image_dir, pending,
                                 brightness, detail, active_fraction)
                    progress["pending"] = None
                    progress["reference_frame"] = encode(frame)
            else:
                pending["stable"] = 0
            if (progress["pending"] is not None and
                    sample.second - pending["started_at"] >= self.config.max_pending_seconds):
                anchor = reference or decode(pending["start_frame"])
                chosen = pending.get("best_changed_frame") or pending["best_frame"]
                chosen_pixels = decode(chosen["frame"])
                measured = change(anchor, chosen_pixels,
                                  active_threshold=self.config.local_tile_threshold)
                changed = (measured.global_score >= self.config.content_threshold
                           or (measured.local_score >= self.config.local_content_threshold
                               and measured.max_local_score >= self.config.local_peak_threshold
                               and measured.largest_region >= 2))
                if not changed:
                    # The sharpest frame may be the original page. A later
                    # readable page still deserves the fallback opportunity.
                    current_change = change(anchor, frame,
                                            active_threshold=self.config.local_tile_threshold)
                    if (current_change.global_score >= self.config.content_threshold
                            or (current_change.local_score >= self.config.local_content_threshold
                                and current_change.max_local_score >= self.config.local_peak_threshold
                                and current_change.largest_region >= 2)):
                        chosen = current_best
                        chosen_pixels = frame
                        measured = current_change
                        changed = True
                last = progress["candidates"][-1] if progress["candidates"] else None
                enough_gap = (last is None or
                              chosen["timestamp"] - last["timestamp"] >=
                              self.config.min_persistent_gap)
                if changed and enough_gap:
                    fallback = {**pending, "reason": "persistent_content_change",
                                "score": round(measured.global_score, 4),
                                "global_score": round(measured.global_score, 4),
                                "local_score": round(measured.local_score, 4),
                                "changed_region_fraction": round(measured.changed_region_fraction, 4)}
                    self._accept(progress, FrameSample(chosen["timestamp"], chosen_pixels),
                                 source, image_dir, fallback, chosen["brightness"],
                                 chosen["detail"], chosen["active_fraction"])
                    progress["reference_frame"] = chosen["frame"]
                progress["pending"] = None
        elif delta >= self.config.scene_threshold:
            progress["pending"] = event("scene_change", change(previous, frame),
                                         sample.second, 0)
        elif reference is not None and delta <= self.config.stability_threshold:
            measured = change(reference, frame,
                              active_threshold=self.config.local_tile_threshold)
            if measured.global_score >= self.config.content_threshold:
                reason = "content_change"
            elif (measured.local_score >= self.config.local_content_threshold
                  and measured.max_local_score >= self.config.local_peak_threshold
                  and measured.largest_region >= 2):
                reason = "local_content_change"
            else:
                reason = None
            if reason:
                progress["pending"] = event(reason, measured, sample.second, 0)
        progress["previous_frame"] = encode(frame)

    def _find_duplicate(self, candidates: list[dict], sample_preview: bytes,
                        sample_hashes: list[str]) -> tuple[dict | None, float | None, float | None, str | None]:
        best = None
        best_hash = None
        best_difference = None
        best_kind = None
        best_rank = float("inf")
        for candidate in candidates:
            fingerprint = candidate["fingerprint"]
            distance = hash_distance(fingerprint["hashes"], sample_hashes)
            prior = decode(fingerprint["preview"])
            pixel_difference = difference(prior, sample_preview)
            if distance > 0.28 or pixel_difference > 0.28:
                continue
            measured = change(prior, sample_preview, width=PREVIEW_WIDTH,
                              height=PREVIEW_HEIGHT,
                              active_threshold=self.config.local_tile_threshold)
            local_text_change = (measured.local_score >= self.config.local_content_threshold
                                 and measured.largest_region >= 2
                                 and (measured.changed_region_fraction < 0.50
                                      or (measured.changed_region_fraction <= 0.55
                                          and measured.local_score >=
                                          measured.global_score * 2.5)))
            similar_pixels = pixel_difference <= self.config.similarity_threshold
            similar_structure = (distance <= self.config.perceptual_threshold
                                 and pixel_difference <= 0.16)
            aligned = aligned_difference(prior, sample_preview)
            similar_zoom = aligned <= 0.03
            wide_zoom = False
            if (not local_text_change and distance <= 0.26
                    and measured.changed_region_fraction >= 0.50
                    and pixel_difference > self.config.similarity_threshold):
                wide_zoom = wide_aligned_difference(prior, sample_preview) <= 0.075
            if (local_text_change and not similar_zoom) or not (
                    similar_pixels or similar_structure or similar_zoom or wide_zoom):
                continue
            rank = min(pixel_difference, aligned) + distance / 2
            if rank < best_rank:
                best = candidate
                best_hash = distance
                best_difference = pixel_difference
                best_kind = ("zoom_or_pan" if pixel_difference > self.config.similarity_threshold
                             else "repeat")
                best_rank = rank
        return best, best_hash, best_difference, best_kind

    def _accept(self, progress: dict, sample: FrameSample, source: Path,
                image_dir: Path, pending: dict, brightness: float, detail: float,
                active_fraction: float) -> None:
        progress["raw_candidate_count"] += 1
        candidates = progress["candidates"]
        last = candidates[-1] if candidates else None
        sample_preview = preview(sample.pixels)
        sample_hashes = fingerprints(sample.pixels)
        match, hash_delta, visual_delta, duplicate_kind = self._find_duplicate(
            candidates, sample_preview, sample_hashes)
        prior_difference = (difference(decode(last["fingerprint"]["preview"]), sample_preview)
                            if last else None)
        if match is not None:
            progress["deduplicated_count"] += 1
            events = progress.setdefault("duplicate_events", [])
            events.append({"timestamp": sample.second, "matched_candidate_id": match["candidate_id"],
                           "perceptual_distance": round(hash_delta, 4), "kind": duplicate_kind})
            del events[:-200]
            if (match is not last
                    or sample.second - last["timestamp"] > self.config.min_candidate_gap
                    or detail <= last["stability"]["detail"]):
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
            "global_change_score": pending["global_score"],
            "local_change_score": pending["local_score"],
            "changed_region_fraction": pending["changed_region_fraction"],
            "stability": {"samples": pending["stable"], "brightness": round(brightness, 4),
                          "detail": round(detail, 4),
                          "active_fraction": round(active_fraction, 4)},
            "similarity": {
                "difference_from_previous": round(prior_difference, 4) if prior_difference is not None else None,
                "deduplicated": replaced,
                "perceptual": {"nearest_candidate_id": match["candidate_id"] if match else None,
                               "hash_distance": round(hash_delta, 4) if hash_delta is not None else None,
                               "visual_difference": round(visual_delta, 4) if visual_delta is not None else None,
                               "kind": duplicate_kind},
            },
            "source_frame": {"video": str(source), "timestamp": sample.second,
                             "detected_at": pending["detected_at"],
                             "sampling_interval": self.config.sampling_interval},
            "fingerprint": {"hashes": sample_hashes, "preview": encode(sample_preview)},
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
    page = [{key: value for key, value in item.items()
             if key not in ("thumbnail", "fingerprint")}
            for item in progress["candidates"][start:start + limit]]
    return {"total": len(progress["candidates"]), "start": start,
            "limit": limit, "candidates": page,
            "scanned_duration": progress["scanned_until"], "complete": progress["complete"]}
