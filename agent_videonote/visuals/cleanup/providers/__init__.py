"""Cleanup provider adapters. Heavy third-party engines stay external."""

from .opencv import OpenCVInpaintStrategy
from .propainter import ProPainterCleanupStrategy
from .vsr import VsrLamaCleanupStrategy, VsrSttnCleanupStrategy

__all__ = [
    "OpenCVInpaintStrategy",
    "ProPainterCleanupStrategy",
    "VsrLamaCleanupStrategy",
    "VsrSttnCleanupStrategy",
]
