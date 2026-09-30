from pathlib import Path
import sys

from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry
from agent_videonote.visuals.cleanup.providers.propainter import ProPainterCleanupStrategy
from agent_videonote.visuals.cleanup.providers.vsr import VsrLamaCleanupStrategy
from agent_videonote.visuals.cleanup.types import CleanupRequest
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig


def test_default_registry_exposes_provider_adapters() -> None:
    registry = build_default_cleanup_registry()
    providers = {item["strategy_id"]: item for item in registry.capabilities()}

    assert {
        "source-frame-replacement",
        "opencv",
        "vsr-lama",
        "vsr-sttn",
        "propainter",
    } <= providers.keys()
    assert providers["vsr-lama"]["automatic_text_removal"] is False
    assert providers["propainter"]["automatic_text_removal"] is False
    assert providers["vsr-lama"]["single_python"] == sys.executable
    assert providers["propainter"]["single_python"] == sys.executable


def test_generated_pixel_provider_requires_explicit_selection(tmp_path: Path) -> None:
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    request = CleanupRequest(
        image_path=str(tmp_path / "candidate.jpg"),
        source_video=str(tmp_path / "video.mp4"),
        hints={"mask_path": str(mask)},
    )

    result = build_default_cleanup_registry().resolve(request)

    assert result.status == "unresolved"
    assert result.strategy_id == "none"
    assert result.detail["attempts"] == []


def test_vsr_lama_reports_unavailable_without_model(tmp_path: Path) -> None:
    root = tmp_path / "vsr"
    (root / "backend" / "inpaint").mkdir(parents=True)
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    runtime = VisualRuntimeConfig(
        vsr_root=str(root),
        lama_model=str(tmp_path / "missing-lama.pt"),
    )
    strategy = VsrLamaCleanupStrategy(runtime)

    result = strategy.clean(CleanupRequest(
        image_path=str(tmp_path / "candidate.jpg"),
        source_video=str(tmp_path / "video.mp4"),
        hints={"provider": "vsr-lama", "mask_path": str(mask)},
    ))

    assert result.status == "unresolved"
    assert result.detail["unresolved_reason"] == "provider_unavailable"
    assert "Big-LaMa model not found" in result.detail["provider_reason"]


def test_propainter_reuses_vsr_source_and_shared_weights(tmp_path: Path) -> None:
    root = tmp_path / "vsr"
    (root / "backend" / "inpaint").mkdir(parents=True)
    (root / "backend" / "inpaint" / "propainter_inpaint.py").write_text(
        "# fake", encoding="utf-8"
    )
    model_dir = tmp_path / "models" / "propainter"
    model_dir.mkdir(parents=True)
    runtime = VisualRuntimeConfig(
        vsr_root=str(root),
        propainter_model_dir=str(model_dir),
    )
    strategy = ProPainterCleanupStrategy(runtime)
    capabilities = strategy.capabilities()

    assert capabilities["single_python"] == sys.executable
    assert "ProPainter weights are missing" in capabilities["reason"]
    assert "inference_propainter.py" not in capabilities["reason"]
