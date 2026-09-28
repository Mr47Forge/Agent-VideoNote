from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.types import CleanupRequest


def test_no_matching_cleanup_strategy_returns_unresolved() -> None:
    registry = CleanupRegistry()
    result = registry.resolve(
        CleanupRequest(image_path="a.jpg", source_video="video.mp4")
    )

    assert not result.resolved
    assert result.status == "unresolved"
