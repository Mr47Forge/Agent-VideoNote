from pathlib import Path

from agent_videonote.application.health_ops import HealthOperationsMixin
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.visuals.cleanup.factory import build_default_cleanup_registry


class HealthHarness(HealthOperationsMixin):
    pass


def _harness(
    tmp_path: Path,
    *,
    roles: dict[str, str | None],
    ffmpeg_exists: bool = True,
    ffprobe_exists: bool = True,
) -> HealthHarness:
    ffmpeg = tmp_path / "ffmpeg-bin"
    ffprobe = tmp_path / "ffprobe-bin"
    if ffmpeg_exists:
        ffmpeg.write_bytes(b"fake")
    if ffprobe_exists:
        ffprobe.write_bytes(b"fake")

    root = tmp_path / "data"
    harness = HealthHarness()
    harness.config = RuntimeConfig(
        paths=RuntimePaths(
            root=root,
            tasks=root / "tasks",
            models=root / "models",
            context=root / "context",
            backups=root / "backups",
        ),
        ffmpeg_bin=str(ffmpeg),
        ffprobe_bin=str(ffprobe),
    )
    harness.asr_registry = ProviderRegistry()
    harness.asr_profile = AsrProfile(roles=roles)
    harness.cleanup_registry = build_default_cleanup_registry()
    return harness


def test_health_is_ok_without_loading_models_when_core_tools_exist(tmp_path: Path) -> None:
    harness = _harness(tmp_path, roles={"primary": None, "review": None})

    result = harness.health()

    assert result["status"] == "ok"
    assert result["models_loaded"] is False
    assert result["warnings"] == []
    assert result["media"]["ffmpeg"]
    assert result["media"]["ffprobe"]
    cleanup = {item["strategy_id"]: item for item in result["visual_cleanup"]["providers"]}
    assert {"source-frame-replacement", "opencv", "vsr-lama", "propainter"} <= cleanup.keys()


def test_health_reports_configuration_problems_without_crashing(tmp_path: Path) -> None:
    harness = _harness(
        tmp_path,
        roles={"primary": "missing-provider", "review": None},
        ffprobe_exists=False,
    )

    result = harness.health()

    assert result["status"] == "degraded"
    assert result["models_loaded"] is False
    assert result["asr"]["roles"]["primary"]["registered"] is False
    assert any("unregistered provider" in item for item in result["warnings"])
    assert any("ffprobe not found" in item for item in result["warnings"])
