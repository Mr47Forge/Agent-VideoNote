"""Conservative, bounded search for a real clean frame near a candidate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult
from agent_videonote.visuals.discovery.features import (
    HEIGHT, TILE_COLUMNS, TILE_ROWS, WIDTH, change, decode, difference,
    fingerprints, hash_distance, preview,
)
from agent_videonote.visuals.discovery.scene import FrameSample, FrameSampler


@dataclass(frozen=True)
class SourceSearchConfig:
    radius_seconds: float = 5.0
    sampling_interval: float = 1.0
    max_samples: int = 16

    def __post_init__(self) -> None:
        if not 2 <= self.radius_seconds <= 6:
            raise ValueError("radius_seconds must be between 2 and 6")
        if not 0.5 <= self.sampling_interval <= 1:
            raise ValueError("sampling_interval must be between 0.5 and 1")
        if not 4 <= self.max_samples <= 20:
            raise ValueError("max_samples must be between 4 and 20")
        required = math.ceil(2 * self.radius_seconds / self.sampling_interval) + 2
        if required > self.max_samples:
            raise ValueError("search window exceeds max_samples")


@dataclass(frozen=True)
class CleanFrameSelection:
    timestamp: float
    confidence: float
    evidence: dict[str, float | int]


def _detail(frame: bytes) -> float:
    total = 0
    for y in range(1, HEIGHT):
        row = y * WIDTH
        for x in range(1, WIDTH):
            index = row + x
            total += abs(frame[index] - frame[index - 1])
            total += abs(frame[index] - frame[index - WIDTH])
    return total / ((WIDTH - 1) * (HEIGHT - 1) * 510)


def _occlusion_evidence(candidate: bytes, clean: bytes) -> dict[str, float | int] | None:
    measured = change(clean, candidate)
    if not (0.015 <= measured.global_score <= 0.15
            and 0 < measured.changed_region_fraction <= 0.40
            and measured.max_local_score >= 0.12
            and measured.largest_region >= 2):
        return None

    # Dense, connected changed tiles identify a transient block rather than
    # sparse glyph changes. This is an occlusion check, not another state hash.
    changed = [0] * (TILE_COLUMNS * TILE_ROWS)
    counts = [0] * len(changed)
    candidate_values: list[int] = []
    clean_values: list[int] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            index = y * WIDTH + x
            tile = min(TILE_ROWS - 1, y * TILE_ROWS // HEIGHT) * TILE_COLUMNS
            tile += min(TILE_COLUMNS - 1, x * TILE_COLUMNS // WIDTH)
            counts[tile] += 1
            if abs(candidate[index] - clean[index]) >= 32:
                changed[tile] += 1
                candidate_values.append(candidate[index])
                clean_values.append(clean[index])
    fraction = len(candidate_values) / (WIDTH * HEIGHT)
    dense = sum(amount / count >= 0.45 for amount, count in zip(changed, counts))
    if not (0.035 <= fraction <= 0.35 and dense >= 2):
        return None

    def variance(values: list[int]) -> float:
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / len(values)

    candidate_variance = variance(candidate_values)
    clean_variance = variance(clean_values)
    contrast = abs(sum(candidate_values) - sum(clean_values)) / len(candidate_values)
    # A genuine chat bubble or changed slide text can be a dense local change.
    # Phase 1 only accepts a nearly uniform opaque covering block; textured
    # advertisements remain unresolved until stronger evidence is available.
    if not (candidate_variance <= 100 and contrast >= 45):
        return None
    return {
        "global_difference": round(measured.global_score, 4),
        "changed_region_fraction": round(measured.changed_region_fraction, 4),
        "occluded_pixel_fraction": round(fraction, 4),
        "dense_changed_tiles": dense,
        "candidate_variance": round(candidate_variance, 2),
        "clean_variance": round(clean_variance, 2),
    }


def select_clean_frame(candidate: FrameSample, nearby: list[FrameSample],
                       config: SourceSearchConfig) -> tuple[CleanFrameSelection | None, str]:
    if len(nearby) + 1 > config.max_samples:
        raise ValueError("nearby frame count exceeds max_samples")
    before = [frame for frame in nearby if frame.second < candidate.second - 0.5]
    after = [frame for frame in nearby if frame.second > candidate.second + 0.5]
    if not before or not after:
        return None, "no_two_sided_same_state_witness"

    candidate_hashes = fingerprints(candidate.pixels)
    best: tuple[float, CleanFrameSelection] | None = None
    witnessed_pair = False
    for left in before:
        for right in after:
            agreement = difference(left.pixels, right.pixels)
            if agreement > 0.025 or hash_distance(
                    fingerprints(left.pixels), fingerprints(right.pixels)) > 0.12:
                continue
            witnessed_pair = True
            for clean in (left, right):
                if hash_distance(candidate_hashes, fingerprints(clean.pixels)) > 0.28:
                    continue
                evidence = _occlusion_evidence(candidate.pixels, clean.pixels)
                if evidence is None:
                    continue
                quality = _detail(clean.pixels)
                rank = quality - agreement * 0.1
                selection = CleanFrameSelection(
                    timestamp=clean.second,
                    confidence=round(min(0.98, 0.80 +
                                         float(evidence["occluded_pixel_fraction"]) * 0.5 -
                                         agreement), 3),
                    evidence={**evidence, "witness_agreement": round(agreement, 4),
                              "replacement_detail": round(quality, 4)},
                )
                if best is None or rank > best[0]:
                    best = (rank, selection)
    if best is not None:
        return best[1], "verified_transient_occlusion"
    if witnessed_pair:
        return None, "no_verified_clean_frame"
    return None, "no_two_sided_same_state_witness"


class SourceFrameCleanup:
    """Extract only the selected full-size frame into task temp, then reuse the strategy."""

    def __init__(self, media, sampler: FrameSampler, registry: CleanupRegistry,
                 config: SourceSearchConfig | None = None) -> None:
        self.media = media
        self.sampler = sampler
        self.registry = registry
        self.config = config or SourceSearchConfig()

    def clean(self, *, source: Path, candidate: dict, duration: float,
              temp_dir: Path, output_path: Path) -> CleanupResult:
        timestamp = float(candidate["timestamp"])
        interval = self.config.sampling_interval
        start = max(0.0, timestamp - self.config.radius_seconds - interval / 2)
        end = min(duration, timestamp + self.config.radius_seconds + interval / 2)
        nearby = self.sampler.sample(source, start, end - start, interval)
        current_sample = min(
            nearby,
            key=lambda frame: abs(frame.second - timestamp),
            default=None,
        )
        extra_samples = 0
        if (current_sample is None
                or abs(current_sample.second - timestamp) > interval * 0.55):
            exact_start = max(0.0, timestamp - interval / 2)
            exact = self.sampler.sample(
                source,
                exact_start,
                min(interval, duration - exact_start),
                interval,
            )
            extra_samples = len(exact)
            if not exact:
                raise ValueError("candidate source frame is unavailable")
            current_sample = exact[0]
        if len(nearby) + extra_samples > self.config.max_samples:
            raise ValueError("nearby frame count exceeds max_samples")
        current = FrameSample(timestamp, current_sample.pixels)
        stored_preview = decode(candidate.get("fingerprint", {}).get("preview"))
        if stored_preview is None or difference(preview(current.pixels), stored_preview) > 0.06:
            raise ValueError("candidate frame does not match its discovery preview")
        selection, reason = select_clean_frame(current, nearby, self.config)
        if selection is None:
            return CleanupResult(
                status="clean", output_path=str(candidate["image_path"]),
                strategy_id="source-frame-replacement",
                detail={"evidence": {"assessment": "no_cleanup_required_by_current_evidence",
                                     "search_reason": reason,
                                     "sample_count": len(nearby) + extra_samples}},
            )

        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_frame = temp_dir / f"source-{selection.timestamp:.3f}.jpg"
        try:
            self.media.extract_frame(source, temp_frame, second=selection.timestamp)
            request = CleanupRequest(
                image_path=candidate["image_path"], source_video=str(source),
                output_path=str(output_path), nearby_frame_paths=(str(temp_frame),),
                hints={"clean_frame_path": str(temp_frame)},
            )
            result = self.registry.resolve(request)
            if not result.resolved:
                return CleanupResult(
                    status="unresolved", output_path=None,
                    strategy_id="source-frame-replacement",
                    detail={"unresolved_reason": "replacement_strategy_rejected",
                            "evidence": {**selection.evidence,
                                         "sample_count": len(nearby) + extra_samples}},
                )
            return CleanupResult(
                status="resolved", output_path=result.output_path,
                strategy_id=result.strategy_id,
                detail={"replacement_timestamp": selection.timestamp,
                        "confidence": selection.confidence,
                        "evidence": {**selection.evidence,
                                     "sample_count": len(nearby) + extra_samples}},
            )
        finally:
            temp_frame.unlink(missing_ok=True)
            try:
                temp_dir.rmdir()
            except OSError:
                pass
