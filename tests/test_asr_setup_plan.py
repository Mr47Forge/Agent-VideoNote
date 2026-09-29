from pathlib import Path

from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.runtime_config import AsrRuntimeConfig, ProviderSpec
from agent_videonote.asr.setup import plan
from agent_videonote.core.config import RuntimeConfig, RuntimePaths


def test_setup_plan_reuses_configured_model_directory_without_installing(tmp_path: Path, monkeypatch) -> None:
    models = tmp_path / "asr_models"
    local_model = models / "FunAudioLLM" / "Fun-ASR-Nano-2512"
    local_model.mkdir(parents=True)
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_bytes(b"x")
    monkeypatch.setattr(plan, "_nvidia_gpu", lambda path: {"available": False, "devices": [], "reason": "test"})
    monkeypatch.setattr(plan, "_package_version", lambda package: None)
    config = RuntimeConfig(
        paths=RuntimePaths(tmp_path, tmp_path / "tasks", models, tmp_path / "context", tmp_path / "backups"),
        ffmpeg_bin=str(ffmpeg), ffprobe_bin=str(tmp_path / "missing-ffprobe"),
    )
    asr = AsrRuntimeConfig(
        profile=AsrProfile(roles={"primary": "local", "review": None}),
        providers=(ProviderSpec("local", "funasr_auto", {"model": "FunAudioLLM/Fun-ASR-Nano-2512", "device": "cpu"}),),
    )

    result = plan.asr_setup_plan(config, asr)

    assert result["mode"] == "plan_only"
    assert result["installs_performed"] is False
    assert result["downloads_performed"] is False
    assert result["configuration"]["providers"][0]["local_model"] == str(local_model)
    assert result["configuration"]["providers"][0]["model_download_needed"] is False
    assert result["estimated_model_download_gb"] == 0
    assert result["runtime_packages_to_install"] == ["funasr", "torch"]
    assert "ffprobe" in result["missing"]
    assert result["recommended_models"][0]["target_dir"].startswith(str(models))


def test_setup_plan_reports_unconfigured_roles_and_supported_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(plan, "_nvidia_gpu", lambda path: {"available": False, "devices": [], "reason": "test"})
    monkeypatch.setattr(plan, "_package_version", lambda package: None)
    paths = RuntimePaths(tmp_path, tmp_path / "tasks", tmp_path / "asr_models", tmp_path / "context", tmp_path / "backups")
    result = plan.asr_setup_plan(
        RuntimeConfig(paths),
        AsrRuntimeConfig(AsrProfile(roles={"primary": None, "review": None}), ()),
    )
    assert "ASR Provider/Profile configuration" in result["missing"]
    assert {item["driver"] for item in result["recommended_models"]} == {"funasr_auto", "qwen_asr"}
