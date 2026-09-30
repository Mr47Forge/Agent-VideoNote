from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agent_videonote.core.config import RuntimeConfig
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig


VSR_REPOSITORY = "https://github.com/YaoFANGUK/video-subtitle-remover.git"
VSR_REVISION = "e109b9ddc1d0e8f153199dfa05c1d767546906d8"
VSR_RAW_ROOT = (
    "https://raw.githubusercontent.com/"
    f"YaoFANGUK/video-subtitle-remover/{VSR_REVISION}"
)

_MINIMAL_PACKAGES = {
    "cv2": "opencv-python-headless>=4.11,<5",
    "PIL": "Pillow>=10",
    "scipy": "scipy>=1.11",
    "einops": "einops>=0.7",
    "tqdm": "tqdm>=4.66",
}

_TORCHVISION_BY_TORCH = {
    "2.3": "0.18",
    "2.4": "0.19",
    "2.5": "0.20",
    "2.6": "0.21",
    "2.7": "0.22",
    "2.8": "0.23",
}

_BIG_LAMA_PARTS = (
    ("backend/models/big-lama/big-lama_1.pt", "00851904b2a962f345adc2efbf9b5284c74e2fcd", 50000000),
    ("backend/models/big-lama/big-lama_2.pt", "ca8e0ad2cd4d632507f5b058d7add3bd50860258", 50000000),
    ("backend/models/big-lama/big-lama_3.pt", "063c1fb7b5f792c675dedd3460b44ab1f450736a", 50000000),
    ("backend/models/big-lama/big-lama_4.pt", "7e8fdcc6cd35047e6b4733358c9f59d35ff92ad9", 50000000),
    ("backend/models/big-lama/big-lama_5.pt", "9198d0b5947f314d55d711d86838222c5141db6c", 5803670),
)

_PROPAINTER_PARTS = (
    ("backend/models/propainter/ProPainter_1.pth", "0a85ad6c75722dcbdbfb36503d71879a0094a7e7", 50000000),
    ("backend/models/propainter/ProPainter_2.pth", "948aebc0a4b40a3292b663f1e86e5a10fa7dd64e", 50000000),
    ("backend/models/propainter/ProPainter_3.pth", "cc3586ee07055120466a18310f03d28a4b481723", 50000000),
    ("backend/models/propainter/ProPainter_4.pth", "aff41a08552c472a88d278361472b24a07cf2bee", 7780510),
)

_DIRECT_MODELS = (
    (
        "backend/models/sttn-det/sttn.pth",
        "4b9c2458591463af28c8f5b7044a09f8689f87c1",
        66252587,
        "sttn.pth",
    ),
    (
        "backend/models/propainter/raft-things.pth",
        "dbe6f9ffb66f7479f3c6ca2111484670dc6bdc54",
        21108000,
        "propainter/raft-things.pth",
    ),
    (
        "backend/models/propainter/recurrent_flow_completion.pth",
        "28d11eaa68d65880ccae01c1bf9a9d6fe40490ed",
        20348681,
        "propainter/recurrent_flow_completion.pth",
    ),
)


@dataclass(frozen=True)
class VisualSetupPaths:
    source_root: Path
    model_root: Path
    runtime_config: Path


def visual_setup(
    config: RuntimeConfig,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan or install visual cleanup runtime into the current Python environment.

    This never creates another virtual environment. Third-party source and model
    files live under the Agent-VideoNote data/model roots, while Python packages
    are installed into sys.executable's environment only.
    """
    paths = _paths(config)
    current = VisualRuntimeConfig.load(paths.runtime_config)
    report = _status(paths, current)
    if not apply:
        return {
            "apply": False,
            "single_python": sys.executable,
            "creates_virtualenv": False,
            "paths": _path_summary(paths),
            "status": report,
            "planned_actions": _planned_actions(report),
        }

    _require_current_environment()
    actions: list[str] = []
    _install_minimal_dependencies(actions)
    _install_matching_torchvision(actions)
    _install_vsr_source(paths.source_root, actions)
    _install_models(paths.model_root, actions)

    runtime = VisualRuntimeConfig(
        vsr_revision=VSR_REVISION,
        vsr_root=str(paths.source_root.resolve()),
        lama_model=str((paths.model_root / "big-lama.pt").resolve()),
        sttn_model=str((paths.model_root / "sttn.pth").resolve()),
        propainter_model_dir=str((paths.model_root / "propainter").resolve()),
    )
    runtime.save(paths.runtime_config)
    final_status = _status(paths, runtime)
    return {
        "apply": True,
        "single_python": sys.executable,
        "creates_virtualenv": False,
        "paths": _path_summary(paths),
        "actions": actions,
        "status": final_status,
        "runtime_config": str(paths.runtime_config),
        "restart_required": True,
    }


def _paths(config: RuntimeConfig) -> VisualSetupPaths:
    return VisualSetupPaths(
        source_root=config.paths.root / "third_party" / "video-subtitle-remover",
        model_root=config.paths.models / "visual-cleanup",
        runtime_config=config.paths.context / "visual-runtime.json",
    )


def _path_summary(paths: VisualSetupPaths) -> dict[str, str]:
    return {
        "source_root": str(paths.source_root),
        "model_root": str(paths.model_root),
        "runtime_config": str(paths.runtime_config),
    }


def _status(paths: VisualSetupPaths, runtime: VisualRuntimeConfig) -> dict[str, Any]:
    source_ok = (
        paths.source_root.is_dir()
        and (paths.source_root / "backend" / "inpaint" / "lama_inpaint.py").is_file()
        and (paths.source_root / "backend" / "inpaint" / "sttn_det_inpaint.py").is_file()
        and (paths.source_root / "backend" / "inpaint" / "propainter_inpaint.py").is_file()
    )
    models = {
        "lama": paths.model_root / "big-lama.pt",
        "sttn": paths.model_root / "sttn.pth",
        "propainter": paths.model_root / "propainter" / "ProPainter.pth",
        "raft": paths.model_root / "propainter" / "raft-things.pth",
        "flow_completion": paths.model_root / "propainter" / "recurrent_flow_completion.pth",
    }
    return {
        "source_ready": source_ok,
        "revision": runtime.vsr_revision,
        "packages": {
            name: importlib.util.find_spec(name) is not None
            for name in (*_MINIMAL_PACKAGES.keys(), "torch", "torchvision")
        },
        "models": {
            name: {"ready": path.is_file(), "path": str(path)}
            for name, path in models.items()
        },
        "runtime_config_exists": paths.runtime_config.is_file(),
    }


def _planned_actions(status: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    missing_packages = [name for name, ready in status["packages"].items() if not ready]
    if missing_packages:
        actions.append("install_missing_packages:" + ",".join(missing_packages))
    if not status["source_ready"]:
        actions.append("install_vsr_sparse_source")
    missing_models = [
        name for name, item in status["models"].items() if not item["ready"]
    ]
    if missing_models:
        actions.append("download_models:" + ",".join(missing_models))
    if not status["runtime_config_exists"]:
        actions.append("write_visual_runtime_config")
    return actions


def _require_current_environment() -> None:
    prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    if prefix == base:
        raise RuntimeError(
            "visual_setup refuses to install into the global Python environment; "
            "run it from the existing Agent-VideoNote virtual environment"
        )


def _install_minimal_dependencies(actions: list[str]) -> None:
    missing = [
        package for module, package in _MINIMAL_PACKAGES.items()
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        return
    _run([sys.executable, "-m", "pip", "install", *missing])
    actions.append("installed_minimal_visual_dependencies")


def _install_matching_torchvision(actions: list[str]) -> None:
    if importlib.util.find_spec("torch") is None:
        raise RuntimeError(
            "PyTorch is missing from the Agent-VideoNote environment. "
            "Install the normal GPU runtime first; visual_setup will not create "
            "a second environment or guess a different Torch build."
        )
    if importlib.util.find_spec("torchvision") is not None:
        return

    import torch

    version = ".".join(torch.__version__.split("+", 1)[0].split(".")[:2])
    tv = _TORCHVISION_BY_TORCH.get(version)
    if tv is None:
        raise RuntimeError(
            f"no safe torchvision mapping is defined for torch {torch.__version__}"
        )
    command = [
        sys.executable, "-m", "pip", "install",
        f"torchvision~={tv}.0", "--no-deps",
    ]
    cuda = getattr(torch.version, "cuda", None)
    if cuda:
        index = "cu" + cuda.replace(".", "")
        command.extend(["--index-url", f"https://download.pytorch.org/whl/{index}"])
    _run(command)
    actions.append(f"installed_torchvision_for_torch_{version}")


def _install_vsr_source(root: Path, actions: list[str]) -> None:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is required to install the VSR source")
    if root.is_dir() and (root / ".git").is_dir():
        current = _capture([git, "-C", str(root), "rev-parse", "HEAD"]).strip()
        if current == VSR_REVISION:
            return
        _run([git, "-C", str(root), "fetch", "origin", VSR_REVISION, "--depth", "1"])
    else:
        if root.exists():
            raise RuntimeError(f"visual third-party path exists but is not a git repo: {root}")
        root.parent.mkdir(parents=True, exist_ok=True)
        _run([
            git, "clone", "--filter=blob:none", "--no-checkout",
            VSR_REPOSITORY, str(root),
        ])
        _run([git, "-C", str(root), "fetch", "origin", VSR_REVISION, "--depth", "1"])

    _run([git, "-C", str(root), "sparse-checkout", "init", "--no-cone"])
    _run([
        git, "-C", str(root), "sparse-checkout", "set",
        "/backend/__init__.py",
        "/backend/inpaint/",
        "/backend/tools/inpaint_tools.py",
    ])
    _run([git, "-C", str(root), "checkout", "--detach", VSR_REVISION])
    actions.append(f"installed_vsr_source:{VSR_REVISION}")


def _install_models(root: Path, actions: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "big-lama.pt").is_file():
        _download_joined(_BIG_LAMA_PARTS, root / "big-lama.pt")
        actions.append("downloaded_big_lama")
    if not (root / "propainter" / "ProPainter.pth").is_file():
        _download_joined(_PROPAINTER_PARTS, root / "propainter" / "ProPainter.pth")
        actions.append("downloaded_propainter")
    for remote, blob_sha, size, relative in _DIRECT_MODELS:
        target = root / relative
        if target.is_file():
            continue
        _download_blob(remote, blob_sha, size, target)
        actions.append(f"downloaded_{Path(relative).name}")


def _download_joined(parts: Iterable[tuple[str, str, int]], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return
    with tempfile.TemporaryDirectory(prefix="agent-videonote-model-", dir=target.parent) as temp:
        temp_root = Path(temp)
        assembled = temp_root / (target.name + ".assembled")
        with assembled.open("wb") as output:
            for index, (remote, blob_sha, size) in enumerate(parts):
                part = temp_root / f"part-{index:02d}"
                _download_verified(remote, blob_sha, size, part)
                with part.open("rb") as handle:
                    shutil.copyfileobj(handle, output, length=1024 * 1024)
        os.replace(assembled, target)


def _download_blob(remote: str, blob_sha: str, size: int, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-videonote-model-", dir=target.parent) as temp:
        part = Path(temp) / target.name
        _download_verified(remote, blob_sha, size, part)
        os.replace(part, target)


def _download_verified(remote: str, blob_sha: str, size: int, target: Path) -> None:
    url = f"{VSR_RAW_ROOT}/{remote}"
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    actual_size = target.stat().st_size
    if actual_size != size:
        raise RuntimeError(
            f"downloaded model part has wrong size: {remote}: {actual_size} != {size}"
        )
    actual_blob = _git_blob_sha1(target)
    if actual_blob != blob_sha:
        raise RuntimeError(
            f"downloaded model part failed Git blob verification: {remote}"
        )


def _git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"required executable not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"visual setup command failed ({exc.returncode}): {' '.join(command)}"
        ) from exc


def _capture(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"visual setup command failed: {' '.join(command)}") from exc
    return result.stdout


def runtime_manifest(config: RuntimeConfig) -> dict[str, Any]:
    path = config.paths.context / "visual-runtime.json"
    runtime = VisualRuntimeConfig.load(path)
    return {
        "path": str(path),
        "config": json.loads(json.dumps(runtime.__dict__)),
        "single_python": sys.executable,
        "creates_virtualenv": False,
    }
