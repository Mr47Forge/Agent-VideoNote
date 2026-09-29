from __future__ import annotations

import gc
from threading import Condition, RLock

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.providers.base import AsrProvider
from agent_videonote.asr.request import TranscriptionRequest
from agent_videonote.core.errors import CapabilityError, ConfigurationError
from agent_videonote.transcripts.types import Transcript


class ProviderRegistry:
    """Own provider residency and keep at most one GPU provider loaded."""

    def __init__(self) -> None:
        self._providers: dict[str, AsrProvider] = {}
        self._loaded: set[str] = set()
        self._active: dict[str, int] = {}
        self._active_gpu: str | None = None
        self._condition = Condition(RLock())

    def register(self, provider: AsrProvider) -> None:
        provider_id = provider.provider_id.strip()
        if not provider_id:
            raise ConfigurationError("provider_id cannot be empty")
        with self._condition:
            if provider_id in self._providers:
                raise ConfigurationError(f"duplicate ASR provider: {provider_id}")
            self._providers[provider_id] = provider

    def get(
        self,
        provider_id: str,
        required: set[AsrCapability] | frozenset[AsrCapability] = frozenset(),
    ) -> AsrProvider:
        with self._condition:
            provider = self._provider(provider_id)
            missing = set(required) - set(provider.capabilities)
            if missing:
                names = ", ".join(sorted(item.value for item in missing))
                raise CapabilityError(f"provider {provider_id} missing capabilities: {names}")
        return _ManagedProvider(self, provider_id)

    def _provider(self, provider_id: str) -> AsrProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ConfigurationError(f"ASR provider not registered: {provider_id}") from exc

    def _transcribe(self, provider_id: str, request: TranscriptionRequest) -> Transcript:
        with self._condition:
            provider = self._provider(provider_id)
            gpu = AsrCapability.GPU in provider.capabilities
            if gpu:
                while self._active_gpu not in (None, provider_id):
                    self._condition.wait()
                for other_id in self._providers:
                    if other_id != provider_id and self._is_gpu(other_id) and self._is_loaded(other_id):
                        self._release_locked(other_id)
                self._active_gpu = provider_id
            self._active[provider_id] = self._active.get(provider_id, 0) + 1
        try:
            return provider.transcribe(request)
        finally:
            with self._condition:
                self._refresh_loaded(provider_id, attempted=True)
                self._active[provider_id] -= 1
                if self._active[provider_id] == 0:
                    del self._active[provider_id]
                    if self._active_gpu == provider_id:
                        self._active_gpu = None
                self._condition.notify_all()

    def loaded_providers(self) -> list[dict[str, object]]:
        with self._condition:
            return [
                {"provider_id": provider_id, "gpu": self._is_gpu(provider_id)}
                for provider_id in self._providers
                if self._is_loaded(provider_id)
            ]

    def release_provider(self, provider_id: str) -> bool:
        with self._condition:
            self._provider(provider_id)
            while self._active.get(provider_id, 0):
                self._condition.wait()
            return self._release_locked(provider_id)

    def _release_locked(self, provider_id: str) -> bool:
        if not self._is_loaded(provider_id):
            return False
        provider = self._provider(provider_id)
        provider.close()
        gc.collect()
        if self._is_gpu(provider_id):
            try:
                import torch
            except ImportError:
                pass
            else:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        self._refresh_loaded(provider_id)
        if self._is_loaded(provider_id):
            raise RuntimeError(f"ASR provider still holds a model after release: {provider_id}")
        return True

    def _is_gpu(self, provider_id: str) -> bool:
        return AsrCapability.GPU in self._provider(provider_id).capabilities

    def _is_loaded(self, provider_id: str) -> bool:
        state = getattr(self._provider(provider_id), "is_loaded", None)
        return bool(state) if state is not None else provider_id in self._loaded

    def _refresh_loaded(self, provider_id: str, *, attempted: bool = False) -> None:
        state = getattr(self._provider(provider_id), "is_loaded", None)
        if state is True or (state is None and attempted):
            self._loaded.add(provider_id)
        elif state is False or not attempted:
            self._loaded.discard(provider_id)

    def list_capabilities(self) -> dict[str, list[str]]:
        with self._condition:
            return {
                key: sorted(item.value for item in provider.capabilities)
                for key, provider in self._providers.items()
            }

    def preflight(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for provider_id, provider in self._providers.items():
            check = getattr(provider, "preflight", None)
            warnings = tuple(check()) if callable(check) else ()
            result[provider_id] = list(warnings)
        return result

    def close_all(self) -> None:
        for provider_id in tuple(self._providers):
            self.release_provider(provider_id)


class _ManagedProvider:
    """Protocol-compatible handle; all inference passes through the registry."""

    def __init__(self, registry: ProviderRegistry, provider_id: str) -> None:
        self._registry = registry
        self.provider_id = provider_id

    @property
    def capabilities(self) -> frozenset[AsrCapability]:
        return self._registry._provider(self.provider_id).capabilities

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        return self._registry._transcribe(self.provider_id, request)

    def close(self) -> None:
        self._registry.release_provider(self.provider_id)
