from pathlib import Path

from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry
from agent_videonote.visuals.cleanup.providers.propainter import (
    ProPainterCleanupStrategy,
    ProPainterConfig,
)
from agent_videonote.visuals.cleanup.providers.vsr import (
    VsrLamaCleanupStrategy,
    VsrProviderConfig,
)
from agent_videonote.visuals.cleanup.types import CleanupRequest


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


def test_vsr_lama_reports_unavailable_without_downloading(tmp_path: Path) -> None:
    root = tmp_path / "vsr"
    (root / "backend" / "inpaint").mkdir(parents=True)
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    strategy = VsrLamaCleanupStrategy(VsrProviderConfig(
        root=root,
        python_bin="definitely-not-a-real-python-executable",
        lama_model=tmp_path / "missing-lama.pt",
        sttn_model=None,
    ))

    result = strategy.clean(CleanupRequest(
        image_path=str(tmp_path / "candidate.jpg"),
        source_video=str(tmp_path / "video.mp4"),
        hints={"provider": "vsr-lama", "mask_path": str(mask)},
    ))

    assert result.status == "unresolved"
    assert result.detail["unresolved_reason"] == "provider_unavailable"


def test_propainter_refuses_missing_weights_instead_of_auto_downloading(tmp_path: Path) -> None:
    root = tmp_path / "ProPainter"
    root.mkdir()
    (root / "inference_propainter.py").write_text("print('must not run')", encoding="utf-8")
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"mask")
    frames = []
    for index in range(3):
        frame = tmp_path / f"{index}.png"
        frame.write_bytes(b"frame")
        frames.append(str(frame))

    strategy = ProPainterCleanupStrategy(ProPainterConfig(root=root, python_bin="python"))
    result = strategy.clean(CleanupRequest(
        image_path=frames[1],
        source_video=str(tmp_path / "video.mp4"),
        nearby_frame_paths=tuple(frames),
        hints={"provider": "propainter", "mask_path": str(mask)},
    ))

    assert result.status == "unresolved"
    assert result.detail["unresolved_reason"] == "provider_unavailable"
    assert "automatic download is disabled" in result.detail["provider_reason"]
