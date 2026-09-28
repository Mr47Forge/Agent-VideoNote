from pathlib import Path

from agent_videonote.visuals.cleanup.strategies.source_frame import (
    SourceFrameReplacementStrategy,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest


def test_verified_source_frame_is_copied(tmp_path: Path) -> None:
    original = tmp_path / "original.jpg"
    clean = tmp_path / "clean.jpg"
    output = tmp_path / "out.jpg"
    original.write_bytes(b"dirty")
    clean.write_bytes(b"clean")

    strategy = SourceFrameReplacementStrategy()
    request = CleanupRequest(
        image_path=str(original),
        source_video=str(tmp_path / "video.mp4"),
        output_path=str(output),
        nearby_frame_paths=(str(clean),),
        hints={"clean_frame_path": str(clean)},
    )

    assert strategy.can_handle(request)
    result = strategy.clean(request)

    assert result.resolved
    assert output.read_bytes() == b"clean"


def test_unlisted_frame_is_rejected(tmp_path: Path) -> None:
    clean = tmp_path / "clean.jpg"
    clean.write_bytes(b"clean")

    strategy = SourceFrameReplacementStrategy()
    request = CleanupRequest(
        image_path=str(tmp_path / "original.jpg"),
        source_video=str(tmp_path / "video.mp4"),
        hints={"clean_frame_path": str(clean)},
    )

    assert not strategy.can_handle(request)
