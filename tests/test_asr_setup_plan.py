from pathlib import Path
import json

from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.runtime_config import AsrRuntimeConfig, ProviderSpec
from agent_videonote.asr.setup import plan
from agent_videonote.asr.setup.discovery import discovery_roots, find_local_models
from agent_videonote.asr.catalog.builtin import BUILTIN_MODELS
from agent_videonote.core.config import RuntimeConfig, RuntimePaths


def test_setup_plan_reuses_configured_model_directory_without_installing(tmp_path: Path, monkeypatch) -> None:
    models = tmp_path / "asr_models"
    local_model = models / "FunAudioLLM" / "Fun-ASR-Nano-2512"
    local_model.mkdir(parents=True)
    (local_model / "config.yaml").write_text("model: nano", encoding="utf-8")
    (local_model / "model.pt").write_bytes(b"x" * 1_000_001)
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


def test_setup_plan_finds_existing_weights_outside_empty_project_dir(tmp_path: Path, monkeypatch) -> None:
    external = tmp_path / "old-models"
    nano = external / "funasr" / "nano"
    vad = external / "funasr" / "fsmn-vad"
    qwen = external / "qwen3-asr-1.7b"
    for directory in (nano, vad, qwen):
        directory.mkdir(parents=True)
    (nano / "config.yaml").write_text("model: nano", encoding="utf-8")
    (nano / "model.pt").write_bytes(b"x" * 1_000_001)
    (vad / "config.yaml").write_text("model: vad", encoding="utf-8")
    (vad / "model.pt").write_bytes(b"x" * 1_000_001)
    (qwen / "config.json").write_text("{}", encoding="utf-8")
    (qwen / "model.safetensors").write_bytes(b"x" * 1_000_001)
    monkeypatch.setattr(plan, "_nvidia_gpu", lambda path: {"available": False, "devices": [], "reason": "test"})
    monkeypatch.setattr(plan, "_package_version", lambda package: None)
    paths = RuntimePaths(tmp_path, tmp_path / "tasks", tmp_path / "empty-models", tmp_path / "context", tmp_path / "backups")
    asr = AsrRuntimeConfig(
        AsrProfile(roles={"primary": "nano", "review": "qwen"}),
        (
            ProviderSpec("nano", "funasr_auto", {"model": "FunAudioLLM/Fun-ASR-Nano-2512", "vad_model": "fsmn-vad", "device": "cpu"}),
            ProviderSpec("qwen", "qwen_asr", {"model": "Qwen/Qwen3-ASR-1.7B", "device_map": "cpu"}),
        ),
    )

    result = plan.asr_setup_plan(RuntimeConfig(paths), asr, search_dirs=[str(external)])

    providers = {item["role"]: item for item in result["configuration"]["providers"]}
    assert providers["primary"]["local_model"] == str(nano)
    assert providers["primary"]["local_model_verified"] is True
    assert providers["primary"]["suggested_model_path"] == str(nano)
    assert providers["primary"]["uses_absolute_model_path"] is False
    assert providers["primary"]["local_vad_model"] == str(vad)
    assert providers["review"]["local_model"] == str(qwen)
    assert all(item["model_download_needed"] is False for item in providers.values())
    assert result["estimated_model_download_gb"] == 0
    assert result["existing_vad_models"][0]["path"] == str(vad)


def test_discovery_checks_modelscope_and_complete_huggingface_snapshots(tmp_path: Path) -> None:
    ms = tmp_path / "ms"
    nano = ms / "hub" / "models" / "FunAudioLLM" / "Fun-ASR-Nano-2512"
    nano.mkdir(parents=True)
    (nano / "config.yaml").write_text("model: nano", encoding="utf-8")
    (nano / "model.pt").write_bytes(b"x" * 1_000_001)
    hf = tmp_path / "hf"
    qwen = hf / "hub" / "models--Qwen--Qwen3-ASR-1.7B" / "snapshots" / "123"
    qwen.mkdir(parents=True)
    (qwen / "config.json").write_text("{}", encoding="utf-8")
    (qwen / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"one": "model-00001.safetensors", "two": "model-00002.safetensors"}}),
        encoding="utf-8",
    )
    (qwen / "model-00001.safetensors").write_bytes(b"x" * 1_000_001)
    roots = [root for root in discovery_roots(tmp_path / "empty", [str(ms), str(hf)]) if root["source"] == "user_directory"]
    incomplete = find_local_models(BUILTIN_MODELS, roots)
    assert incomplete["fun-asr-nano-2512"][0]["path"] == str(nano)
    assert incomplete["qwen3-asr-1.7b"] == []
    (qwen / "model-00002.safetensors").write_bytes(b"x" * 1_000_001)
    complete = find_local_models(BUILTIN_MODELS, roots)
    assert complete["qwen3-asr-1.7b"][0]["path"] == str(qwen)
