from __future__ import annotations

from agent_videonote.visuals.cleanup.providers import (
    OpenCVInpaintStrategy,
    ProPainterCleanupStrategy,
    VsrLamaCleanupStrategy,
    VsrSttnCleanupStrategy,
)
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.strategies.source_frame import SourceFrameReplacementStrategy


def build_default_cleanup_registry() -> CleanupRegistry:
    registry = CleanupRegistry()
    registry.register(SourceFrameReplacementStrategy())
    registry.register(OpenCVInpaintStrategy())
    registry.register(VsrLamaCleanupStrategy())
    registry.register(VsrSttnCleanupStrategy())
    registry.register(ProPainterCleanupStrategy())
    return registry
