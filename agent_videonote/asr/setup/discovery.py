"""Bounded, read-only discovery of reusable local ASR model weights."""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from agent_videonote.asr.catalog.models import ModelCard


_LAYOUTS = {
    "fun-asr-nano-2512": (("funasr", "nano"), ("Fun-ASR-Nano-2512",)),
    "qwen3-asr-1.7b": (("qwen3-asr-1.7b",), ("Qwen3-ASR-1.7B",)),
}


def discovery_roots(models_dir: Path, extra_dirs: list[str] | None = None) -> list[dict[str, Any]]:
    """Inspect only named locations; never walk a drive or a project tree."""
    home = Path.home()
    drive = Path("D:/") if os.name == "nt" and Path("D:/VideoNote-MCP/运行环境/models").is_dir() else Path(models_dir.anchor or Path.cwd().anchor)
    roots: list[tuple[str, Path]] = [("configured_models_dir", models_dir)]
    roots.extend(("user_directory", Path(value).expanduser()) for value in extra_dirs or [] if value)
    roots.extend(
        ("user_directory", Path(value).expanduser())
        for value in os.getenv("AGENT_VIDEONOTE_MODEL_SEARCH_DIRS", "").split(os.pathsep)
        if value
    )
    roots.extend((
        ("legacy_weights", drive / "VideoNote-MCP" / "运行环境" / "models"),
        ("shared_weights", drive / "AI-Models"),
        ("modelscope_cache", Path(os.getenv("MODELSCOPE_CACHE") or os.getenv("MODELSCOPE_HOME") or home / ".cache" / "modelscope")),
        ("huggingface_cache", Path(os.getenv("HUGGINGFACE_HUB_CACHE") or os.getenv("HF_HOME") or home / ".cache" / "huggingface")),
    ))
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for source, path in roots:
        normalized = path.resolve()
        key = os.path.normcase(str(normalized))
        if key not in seen:
            seen.add(key)
            result.append({"source": source, "path": str(normalized), "exists": normalized.is_dir()})
    return result


def find_local_models(cards: tuple[ModelCard, ...], roots: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = {card.catalog_id: [] for card in cards}
    for card in cards:
        if card.catalog_id not in _LAYOUTS:
            continue
        seen: set[str] = set()
        for root in roots:
            if not root["exists"]:
                continue
            for candidate in _candidates(Path(root["path"]), card):
                if not _valid_weights(candidate, card.catalog_id):
                    continue
                resolved = str(candidate.resolve())
                key = os.path.normcase(resolved)
                if key not in seen:
                    seen.add(key)
                    found[card.catalog_id].append({"path": resolved, "source": root["source"]})
    return found


def find_local_vad(roots: list[dict[str, Any]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for root in roots:
        if not root["exists"]:
            continue
        base = Path(root["path"])
        for path in (base / "funasr" / "fsmn-vad", base / "fsmn-vad", base / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch", base / "hub" / "models" / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch"):
            if not (path / "config.yaml").is_file() or not _large_file(path / "model.pt"):
                continue
            resolved = str(path.resolve())
            key = os.path.normcase(resolved)
            if key not in seen:
                seen.add(key)
                found.append({"path": resolved, "source": root["source"]})
    return found


def _candidates(root: Path, card: ModelCard):
    yield root
    yield root / card.model_id
    for parts in _LAYOUTS[card.catalog_id]:
        yield root.joinpath(*parts)
    # Hugging Face stores repository snapshots behind models--org--name.
    for repo in (
        root / "hub" / ("models--" + card.model_id.replace("/", "--")) / "snapshots",
        root / ("models--" + card.model_id.replace("/", "--")) / "snapshots",
    ):
        if repo.is_dir():
            try:
                yield from (path for path in repo.iterdir() if path.is_dir())
            except OSError:
                pass
    # ModelScope commonly nests models under hub/models/<org>/<name>.
    yield root / "hub" / "models" / card.model_id
    yield root / "models" / card.model_id


def _valid_weights(path: Path, catalog_id: str) -> bool:
    if not path.is_dir():
        return False
    if catalog_id == "fun-asr-nano-2512":
        return (path / "config.yaml").is_file() and _large_file(path / "model.pt")
    if catalog_id == "qwen3-asr-1.7b":
        if not (path / "config.json").is_file():
            return False
        index = path / "model.safetensors.index.json"
        if index.is_file():
            try:
                shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
                return bool(shards) and all(Path(shard).name == shard and _large_file(path / shard) for shard in shards)
            except (OSError, ValueError, KeyError, TypeError):
                return False
        return _large_file(path / "model.safetensors")
    return False


def _large_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 1_000_000
    except OSError:
        return False
