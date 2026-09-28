from __future__ import annotations

from agent_videonote.asr.providers.funasr_auto import FunAsrAutoConfig, FunAsrAutoProvider
from agent_videonote.asr.providers.guard import ConcurrencyGuardProvider
from agent_videonote.asr.providers.qwen_asr import QwenAsrConfig, QwenAsrProvider
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.runtime_config import ProviderSpec
from agent_videonote.core.errors import ConfigurationError


def build_provider(spec: ProviderSpec):
    options = dict(spec.options)

    if spec.driver == "funasr_auto":
        provider = FunAsrAutoProvider(
            FunAsrAutoConfig(provider_id=spec.provider_id, **options)
        )
    elif spec.driver == "qwen_asr":
        provider = QwenAsrProvider(
            QwenAsrConfig(provider_id=spec.provider_id, **options)
        )
    else:
        raise ConfigurationError(f"unknown ASR provider driver: {spec.driver}")

    return ConcurrencyGuardProvider(
        provider,
        max_concurrency=spec.max_concurrency,
    )


def register_provider_specs(
    registry: ProviderRegistry,
    specs: tuple[ProviderSpec, ...],
) -> None:
    for spec in specs:
        registry.register(build_provider(spec))
