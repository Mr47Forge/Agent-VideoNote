from __future__ import annotations

from typing import Any


class LifecycleOperationsMixin:
    def loaded_providers(self) -> list[dict[str, object]]:
        return self.asr_registry.loaded_providers()

    def release_provider(self, provider_id: str) -> dict[str, Any]:
        released = self.asr_registry.release_provider(provider_id)
        return {
            "provider_id": provider_id,
            "released": released,
            "loaded_providers": self.loaded_providers(),
        }

    def release_role(self, role: str) -> dict[str, Any]:
        provider_id = self.asr_profile.provider_for(role)
        if provider_id is None:
            return {"role": role, "provider_id": None, "released": False,
                    "loaded_providers": self.loaded_providers()}
        return {"role": role, **self.release_provider(provider_id)}
