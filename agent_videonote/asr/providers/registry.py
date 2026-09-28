from __future__ import annotations

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.providers.base import AsrProvider
from agent_videonote.core.errors import CapabilityError, ConfigurationError


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AsrProvider] = {}

    def register(self, provider: AsrProvider) -> None:
        provider_id = provider.provider_id.strip()
        if not provider_id:
            raise ConfigurationError("provider_id cannot be empty")
        if provider_id in self._providers:
            raise ConfigurationError(f"duplicate ASR provider: {provider_id}")
        self._providers[provider_id] = provider

    def get(
        self,
        provider_id: str,
        required: set[AsrCapability] | frozenset[AsrCapability] = frozenset(),
    ) -> AsrProvider:
        try:
            provider = self._providers[provider_id]
        except KeyError as exc:
            raise ConfigurationError(f"ASR provider not registered: {provider_id}") from exc

        missing = set(required) - set(provider.capabilities)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise CapabilityError(f"provider {provider_id} missing capabilities: {names}")
        return provider

    def list_capabilities(self) -> dict[str, list[str]]:
        return {
            key: sorted(item.value for item in provider.capabilities)
            for key, provider in self._providers.items()
        }

    def close_all(self) -> None:
        for provider in self._providers.values():
            provider.close()
