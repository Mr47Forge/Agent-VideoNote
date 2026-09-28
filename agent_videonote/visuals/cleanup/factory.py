from __future__ import annotations

from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.strategies.source_frame import SourceFrameReplacementStrategy


def build_default_cleanup_registry() -> CleanupRegistry:
    registry = CleanupRegistry()
    registry.register(SourceFrameReplacementStrategy())
    return registry
