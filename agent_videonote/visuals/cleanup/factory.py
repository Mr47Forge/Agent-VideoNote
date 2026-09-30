from __future__ import annotations

from agent_videonote.visuals.cleanup.providers import (
    OpenCVInpaintStrategy,
    ProPainterCleanupStrategy,
    VsrLamaCleanupStrategy,
    VsrSttnCleanupStrategy,
)
from agent_videonote.visuals.cleanup.registry import CleanupRegistry
from agent_videonote.visuals.cleanup.strategies.source_frame import SourceFrameReplacementStrategy
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig


def build_default_cleanup_registry(
    runtime: VisualRuntimeConfig | None = None,
) -> CleanupRegistry:
    runtime = runtime or VisualRuntimeConfig.disabled()
    registry = CleanupRegistry()
    registry.register(SourceFrameReplacementStrategy())
    registry.register(OpenCVInpaintStrategy())
    registry.register(VsrLamaCleanupStrategy(runtime))
    registry.register(VsrSttnCleanupStrategy(runtime))
    registry.register(ProPainterCleanupStrategy(runtime))
    return registry
