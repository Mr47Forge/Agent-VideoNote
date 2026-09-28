from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_videonote.media.interfaces import MediaBackend
from agent_videonote.visuals.discovery.types import FrameCandidate, VisualState


@dataclass(frozen=True)
class IntervalSamplingConfig:
    target_frames: int = 12
    max_frames: int = 60
    edge_margin_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.target_frames < 1:
            raise ValueError("target_frames must be positive")
        if self.max_frames < self.target_frames:
            raise ValueError("max_frames must be >= target_frames")
        if self.max_frames > 200:
            raise ValueError("max_frames cannot exceed 200")
        if self.edge_margin_seconds < 0:
            raise ValueError("edge_margin_seconds must be >= 0")


class IntervalSamplingDiscovery:
    """Bounded overview sampling. It produces candidates, not final image decisions."""

    strategy_id = "interval-overview"

    def __init__(
        self,
        media: MediaBackend,
        config: IntervalSamplingConfig | None = None,
    ):
        self.media = media
        self.config = config or IntervalSamplingConfig()

    def discover(
        self,
        source: str | Path,
        work_dir: str | Path,
    ) -> tuple[VisualState, ...]:
        info = self.media.probe(source)
        if info.duration is None or info.duration <= 0:
            raise ValueError("media duration is required for interval sampling")

        duration = info.duration
        count = min(self.config.target_frames, self.config.max_frames)
        times = _sample_times(
            duration,
            count=count,
            margin=self.config.edge_margin_seconds,
        )

        output_root = Path(work_dir) / self.strategy_id
        output_root.mkdir(parents=True, exist_ok=True)

        candidates: list[FrameCandidate] = []
        for index, second in enumerate(times, start=1):
            output = output_root / f"{index:03d}-{second:.3f}.jpg"
            if not output.is_file():
                self.media.extract_frame(source, output, second=second)
            candidates.append(
                FrameCandidate(
                    second=second,
                    path=str(output),
                    metadata={"sampling": "interval"},
                )
            )

        # Overview sampling does not pretend to know stable-state boundaries.
        # It returns one overview state that later strategies/Agent inspection can refine.
        return (
            VisualState(
                state_id="overview",
                start=0.0,
                end=duration,
                candidates=tuple(candidates),
                description="bounded interval overview; candidates only",
            ),
        )


def _sample_times(duration: float, *, count: int, margin: float) -> list[float]:
    if count == 1:
        return [max(0.0, min(duration / 2.0, duration - margin))]

    usable_start = min(margin, duration / 2.0)
    usable_end = max(usable_start, duration - margin)
    if usable_end <= usable_start:
        return [duration / 2.0]

    step = (usable_end - usable_start) / (count - 1)
    return [round(usable_start + step * index, 3) for index in range(count)]
