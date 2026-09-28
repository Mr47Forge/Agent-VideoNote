from __future__ import annotations

from typing import Any

from agent_videonote.asr.catalog.builtin import BUILTIN_MODELS
from agent_videonote.asr.catalog.models import ModelCard


_PRIORITY_TERMS = {
    "balanced": (),
    "accuracy": ("质量", "课程", "复核"),
    "speed": ("快", "速度"),
    "multilingual": ("多语言", "语言"),
}


class ModelCatalogService:
    def list_models(
        self,
        *,
        role: str | None = None,
        priority: str = "balanced",
        integrated_only: bool = False,
        limit: int = 5,
        detail: str = "compact",
    ) -> dict[str, Any]:
        if priority not in _PRIORITY_TERMS:
            raise ValueError(
                "priority must be one of: balanced, accuracy, speed, multilingual"
            )
        if limit < 1 or limit > 10:
            raise ValueError("limit must be between 1 and 10")
        if detail not in {"compact", "full"}:
            raise ValueError("detail must be 'compact' or 'full'")

        models = [
            item
            for item in BUILTIN_MODELS
            if (role is None or role in item.fit_roles)
            and (not integrated_only or item.integration_status == "supported")
        ]
        models.sort(key=lambda item: _sort_key(item, priority))

        return {
            "note": (
                "这些是候选建议，不会自动下载安装。识别指标必须结合对应测试集理解，"
                "不同数据集的 WER/CER 不能直接互相当作统一准确率。"
            ),
            "priority": priority,
            "role": role,
            "integrated_only": integrated_only,
            "detail": detail,
            "models": [
                _full_card(item) if detail == "full" else _compact_card(item)
                for item in models[:limit]
            ],
            "total_matches": len(models),
        }


def _sort_key(item: ModelCard, priority: str) -> tuple[int, int, str]:
    integrated_rank = 0 if item.integration_status == "supported" else 1

    if priority == "speed":
        preferred = 0 if ("很快" in item.speed or item.catalog_id == "sensevoice-small") else 1
    elif priority == "accuracy":
        preferred = 0 if item.catalog_id in {"fun-asr-nano-2512", "qwen3-asr-1.7b"} else 1
    elif priority == "multilingual":
        preferred = 0 if item.catalog_id in {"qwen3-asr-1.7b", "whisper-large-v3-turbo"} else 1
    else:
        preferred = integrated_rank

    return preferred, integrated_rank, item.name.casefold()


def _compact_card(item: ModelCard) -> dict[str, Any]:
    benchmark = item.benchmarks[0].to_dict() if item.benchmarks else None
    return {
        "id": item.catalog_id,
        "name": item.name,
        "model_id": item.model_id,
        "integration_status": item.integration_status,
        "provider_driver": item.provider_driver,
        "fit_roles": list(item.fit_roles),
        "speed": item.speed,
        "quality": item.quality,
        "hardware_note": item.hardware_note,
        "strength": item.strengths[0] if item.strengths else None,
        "weakness": item.weaknesses[0] if item.weaknesses else None,
        "representative_benchmark": benchmark,
        "verified_at": item.verified_at,
    }


def _full_card(item: ModelCard) -> dict[str, Any]:
    return {
        "id": item.catalog_id,
        "name": item.name,
        "model_id": item.model_id,
        "integration_status": item.integration_status,
        "provider_driver": item.provider_driver,
        "fit_roles": list(item.fit_roles),
        "languages": item.languages,
        "speed": item.speed,
        "quality": item.quality,
        "hardware_note": item.hardware_note,
        "strengths": list(item.strengths),
        "weaknesses": list(item.weaknesses),
        "capabilities": list(item.capabilities),
        "benchmarks": [value.to_dict() for value in item.benchmarks],
        "license_note": item.license_note,
        "verified_at": item.verified_at,
        "source": item.source,
    }
