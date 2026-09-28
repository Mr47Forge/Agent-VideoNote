from __future__ import annotations

from agent_videonote.asr.providers.funasr_auto import FunAsrAutoConfig, FunAsrAutoProvider
from agent_videonote.asr.providers.guard import ConcurrencyGuardProvider
from agent_videonote.asr.providers.qwen_asr import QwenAsrConfig, QwenAsrProvider
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.runtime_config import ProviderSpec
from agent_videonote.core.errors import ConfigurationError


def build_provider(spec: ProviderSpec):
    options = dict(spec.options)

    try:
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
    except ConfigurationError:
        raise
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"invalid configuration for ASR provider '{spec.provider_id}': {exc}"
        ) from exc

    return ConcurrencyGuardProvider(
        provider,
        max_concurrency=spec.max_concurrency,
    )


def register_provider_specs(
    registry: ProviderRegistry,
    specs: tuple[ProviderSpec, ...],
    *,
    tolerate_errors: bool = False,
) -> tuple[str, ...]:
    warnings: list[str] = []
    for spec in specs:
        try:
            registry.register(build_provider(spec))
        except ConfigurationError as exc:
            if not tolerate_errors:
                raise
            warnings.append(
                f"ASR provider '{spec.provider_id}' was not registered: {exc}"
            )
    return tuple(warnings)
