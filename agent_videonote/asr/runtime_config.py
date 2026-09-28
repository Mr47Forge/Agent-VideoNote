from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.core.errors import ConfigurationError


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    driver: str
    options: dict[str, Any] = field(default_factory=dict)
    max_concurrency: int = 1


@dataclass(frozen=True)
class AsrRuntimeConfig:
    profile: AsrProfile
    providers: tuple[ProviderSpec, ...]


def load_asr_runtime_config(path: str | Path) -> AsrRuntimeConfig:
    source = Path(path).expanduser().resolve(strict=True)
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ConfigurationError("ASR runtime config root must be an object")

    profile = AsrProfile.from_dict({"roles": data.get("roles", {})})

    raw_providers = data.get("providers", [])
    if not isinstance(raw_providers, list):
        raise ConfigurationError("providers must be a list")

    providers: list[ProviderSpec] = []
    seen: set[str] = set()
    for item in raw_providers:
        if not isinstance(item, dict):
            raise ConfigurationError("provider spec must be an object")
        provider_id = str(item.get("id") or "").strip()
        driver = str(item.get("driver") or "").strip()
        options = item.get("options", {})
        max_concurrency = int(item.get("max_concurrency", 1))
        if max_concurrency < 1:
            raise ConfigurationError(
                f"provider max_concurrency must be >= 1: {provider_id or '<unknown>'}"
            )
        if not provider_id or not driver:
            raise ConfigurationError("provider spec requires id and driver")
        if provider_id in seen:
            raise ConfigurationError(f"duplicate provider id: {provider_id}")
        if not isinstance(options, dict):
            raise ConfigurationError(f"provider options must be an object: {provider_id}")
        seen.add(provider_id)
        providers.append(
            ProviderSpec(
                provider_id,
                driver,
                dict(options),
                max_concurrency=max_concurrency,
            )
        )

    return AsrRuntimeConfig(profile=profile, providers=tuple(providers))


def disabled_asr_runtime_config() -> AsrRuntimeConfig:
    return AsrRuntimeConfig(
        profile=AsrProfile(roles={"primary": None, "review": None}),
        providers=(),
    )
