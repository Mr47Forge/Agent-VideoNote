from pathlib import Path

from agent_videonote.application.health_ops import HealthOperationsMixin
from agent_videonote.asr.catalog.service import ModelCatalogService
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.config import RuntimeConfig, RuntimePaths


def test_catalog_can_filter_to_models_already_integrated() -> None:
    result = ModelCatalogService().list_models(
        integrated_only=True,
        limit=10,
    )

    ids = {item["id"] for item in result["models"]}
    assert ids == {"fun-asr-nano-2512", "qwen3-asr-1.7b"}
    assert all(item["integration_status"] == "supported" for item in result["models"])


def test_catalog_default_response_is_compact_and_bounded() -> None:
    result = ModelCatalogService().list_models(limit=2)

    assert result["detail"] == "compact"
    assert len(result["models"]) == 2
    first = result["models"][0]
    assert "strength" in first
    assert "weakness" in first
    assert "representative_benchmark" in first
    assert "strengths" not in first
    assert "benchmarks" not in first


def test_catalog_full_detail_is_explicit_opt_in() -> None:
    result = ModelCatalogService().list_models(
        role="review",
        priority="accuracy",
        integrated_only=True,
        limit=1,
        detail="full",
    )

    assert result["detail"] == "full"
    assert len(result["models"]) == 1
    item = result["models"][0]
    assert item["id"] in {"fun-asr-nano-2512", "qwen3-asr-1.7b"}
    assert "strengths" in item
    assert "weaknesses" in item
    assert "benchmarks" in item


def test_speed_priority_surfaces_speed_focused_candidate() -> None:
    result = ModelCatalogService().list_models(
        priority="speed",
        integrated_only=False,
        limit=1,
    )

    assert result["models"][0]["id"] == "sensevoice-small"


class HealthHarness(HealthOperationsMixin):
    pass


def test_health_points_to_catalog_instead_of_embedding_model_list(tmp_path: Path) -> None:
    root = tmp_path / "data"
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")

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
    harness.asr_profile = AsrProfile(roles={"primary": None, "review": None})
    harness.startup_warnings = ()

    result = harness.health()

    assert result["asr"]["model_help"] == {
        "available": True,
        "tool": "asr_models",
        "reason": "no ASR provider is currently registered",
    }
    assert "models" not in result["asr"]
