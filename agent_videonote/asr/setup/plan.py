from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_videonote.asr.catalog.builtin import BUILTIN_MODELS
from agent_videonote.asr.runtime_config import AsrRuntimeConfig
from agent_videonote.asr.setup.discovery import discovery_roots, find_local_models, find_local_vad
from agent_videonote.core.config import RuntimeConfig


_PACKAGES = {"torch": "torch", "funasr": "funasr", "qwen-asr": "qwen-asr"}
_DRIVER_PACKAGES = {"funasr_auto": ("torch", "funasr"), "qwen_asr": ("torch", "qwen-asr")}
# Advisory weight sizes only. Runtime caches, dependencies and temporary files need extra space.
_MODEL_GB = {"fun-asr-nano-2512": 2.15}


def asr_setup_plan(
    config: RuntimeConfig,
    asr: AsrRuntimeConfig,
    *,
    config_path: Path | None = None,
    search_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect local prerequisites and return a plan; never install or load a model."""
    media = {name: _executable(value) for name, value in (
        ("ffmpeg", config.ffmpeg_bin), ("ffprobe", config.ffprobe_bin)
    )}
    nvidia_smi = shutil.which("nvidia-smi")
    gpu = _nvidia_gpu(nvidia_smi)
    packages = {name: _package_version(dist) for name, dist in _PACKAGES.items()}
    cuda = _torch_cuda() if packages["torch"] else {"available": False, "reason": "torch is not installed"}
    models_dir = config.paths.models.expanduser().resolve()
    roots = discovery_roots(models_dir, search_dirs)
    discovered = find_local_models(BUILTIN_MODELS, roots)
    vad_candidates = find_local_vad(roots)
    free_gb = _free_gb(models_dir)
    selected = []
    needed_packages: set[str] = set()
    missing: list[str] = []
    if not media["ffmpeg"]:
        missing.append("ffmpeg")
    if not media["ffprobe"]:
        missing.append("ffprobe")
    by_id = {item.catalog_id: item for item in BUILTIN_MODELS}
    by_model = {item.model_id: item for item in BUILTIN_MODELS}
    specs = {item.provider_id: item for item in asr.providers}
    for role, provider_id in sorted(asr.profile.roles.items()):
        spec = specs.get(provider_id) if provider_id else None
        if provider_id and spec is None:
            missing.append(f"provider configuration for {role}: {provider_id}")
        if spec is None:
            selected.append({"role": role, "provider": provider_id, "configured": False})
            continue
        for package in _DRIVER_PACKAGES.get(spec.driver, ()):
            if packages[package] is None:
                needed_packages.add(package)
                missing.append(f"Python package: {package}")
        model = str(spec.options.get("model", ""))
        card = by_model.get(model) or by_id.get(model)
        local = _local_model(model, models_dir)
        if local is None and card and discovered[card.catalog_id]:
            local = Path(discovered[card.catalog_id][0]["path"])
        if local and card is None:
            card = next((item for item in BUILTIN_MODELS if any(
                Path(found["path"]) == local for found in discovered[item.catalog_id]
            )), None)
        verified = bool(card and local and any(
            Path(found["path"]) == local for found in discovered[card.catalog_id]
        ))
        needs_cuda = str(spec.options.get("device", spec.options.get("device_map", ""))).lower().startswith("cuda")
        if needs_cuda and cuda["available"] is not True:
            missing.append(f"CUDA unavailable for {role}: {provider_id}")
        if not model:
            missing.append(f"model configuration for {role}: {provider_id}")
        elif local is None:
            missing.append(f"local model for {role}: {model}")
        vad_model = str(spec.options.get("vad_model") or "")
        local_vad = _local_model(vad_model, models_dir) if vad_model else None
        if vad_model and local_vad is None and vad_candidates:
            local_vad = Path(vad_candidates[0]["path"])
        selected.append({
            "role": role, "provider": provider_id, "driver": spec.driver,
            "model": model or None, "local_model": str(local) if local else None,
            "local_model_verified": verified,
            "uses_absolute_model_path": Path(model).is_absolute() if model else False,
            "suggested_model_path": str(local) if local else None,
            "model_download_needed": bool(model and local is None),
            "target_dir": str(models_dir / model) if model and not Path(model).is_absolute() else model or None,
            "estimated_model_gb": _MODEL_GB.get(card.catalog_id) if card else None,
            "vad_model": vad_model or None,
            "local_vad_model": str(local_vad) if local_vad else None,
            "suggested_vad_model_path": str(local_vad) if local_vad else None,
        })
    if not any(item["configured"] if "configured" in item else True for item in selected):
        missing.append("ASR Provider/Profile configuration")

    recommendations = []
    for card in BUILTIN_MODELS:
        if card.integration_status != "supported":
            continue
        recommendations.append({
            "id": card.catalog_id, "model_id": card.model_id,
            "driver": card.provider_driver, "roles": list(card.fit_roles),
            "estimated_model_gb": _MODEL_GB.get(card.catalog_id),
            "local_model": discovered[card.catalog_id][0]["path"] if discovered[card.catalog_id] else None,
            "local_candidates": discovered[card.catalog_id],
            "model_download_needed": not bool(discovered[card.catalog_id]),
            "target_dir": discovered[card.catalog_id][0]["path"] if discovered[card.catalog_id] else str(models_dir / card.model_id),
            "runtime_packages_to_install": [
                item for item in _DRIVER_PACKAGES.get(card.provider_driver or "", ())
                if packages[item] is None
            ],
            "hardware_note": card.hardware_note,
        })
    downloads = [item for item in selected if item.get("model_download_needed")]
    known_download_gb = sum(item["estimated_model_gb"] or 0 for item in downloads)
    return {
        "mode": "plan_only", "installs_performed": False, "downloads_performed": False,
        "media": media, "nvidia": gpu, "torch_cuda": cuda, "packages": packages,
        "configuration": {"path": str(config_path) if config_path else None,
                          "exists": config_path.is_file() if config_path else None,
                          "roles": dict(asr.profile.roles), "providers": selected,
                          "available_providers": [
                              {"id": spec.provider_id, "driver": spec.driver,
                               "model": spec.options.get("model"), "vad_model": spec.options.get("vad_model")}
                              for spec in asr.providers
                          ]},
        "models_dir": str(models_dir), "models_dir_exists": models_dir.is_dir(),
        "models_dir_override": "AGENT_VIDEONOTE_MODEL_DIR",
        "search_roots": roots,
        "existing_models": {key: paths for key, paths in discovered.items() if paths},
        "existing_vad_models": vad_candidates,
        "disk_free_gb": free_gb, "missing": missing,
        "estimated_model_download_gb": round(known_download_gb, 2),
        "model_download_size_unknown": any(item["estimated_model_gb"] is None for item in downloads),
        "runtime_packages_to_install": sorted(needed_packages),
        "recommended_models": recommendations,
        "disk_note": "Model sizes are advisory weight estimates; package/cache/temporary space is additional. Unknown sizes are null.",
        "next_step": "Reuse a discovered absolute model path in Provider/Profile. Install or migrate only as a separate, explicitly chosen action.",
    }


def _executable(value: str) -> str | None:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(value)


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _nvidia_gpu(executable: str | None) -> dict[str, Any]:
    if not executable:
        return {"available": False, "devices": [], "reason": "nvidia-smi not found"}
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return {"available": bool(devices), "devices": devices, "reason": None if devices else "no GPU reported"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "devices": [], "reason": type(exc).__name__}


def _torch_cuda() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import json,torch; print(json.dumps({'available':torch.cuda.is_available(),'torch_cuda_version':torch.version.cuda}))"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return json.loads(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"available": None, "reason": type(exc).__name__}


def _local_model(model: str, models_dir: Path) -> Path | None:
    if not model:
        return None
    path = Path(model).expanduser()
    if path.is_absolute() and path.is_dir():
        return path.resolve()
    if ".." in path.parts:
        return None
    candidate = models_dir / path
    return candidate.resolve() if candidate.is_dir() else None


def _free_gb(path: Path) -> float | None:
    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    try:
        return round(shutil.disk_usage(parent).free / 1_000_000_000, 2)
    except OSError:
        return None
