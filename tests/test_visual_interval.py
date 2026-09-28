from pathlib import Path

from agent_videonote.media.types import MediaInfo
from agent_videonote.visuals.discovery.interval import (
    IntervalSamplingConfig,
    IntervalSamplingDiscovery,
)


class FakeMedia:
    def __init__(self) -> None:
        self.extracted: list[float] = []

    def probe(self, source):
        return MediaInfo(path=str(source), duration=120.0, format_name="fake", streams=())

    def extract_frame(self, source, output, *, second):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpg")
        self.extracted.append(second)
        return path


def test_interval_sampling_is_bounded(tmp_path: Path) -> None:
    media = FakeMedia()
    strategy = IntervalSamplingDiscovery(
        media,
        IntervalSamplingConfig(target_frames=12, max_frames=20),
    )

    states = strategy.discover(tmp_path / "video.mp4", tmp_path / "frames")

    assert len(states) == 1
    assert len(states[0].candidates) == 12
    assert len(media.extracted) == 12
