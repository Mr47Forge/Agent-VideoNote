from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from agent_videonote.workflow.context import runtime_protocol


class HealthOperationsMixin:
    def health(self) -> dict[str, Any]:
        providers = self.asr_registry.list_capabilities()
        provider_preflight = self.asr_registry.preflight()
        loaded = self.asr_registry.loaded_providers()
        gpu_loaded = [item["provider_id"] for item in loaded if item["gpu"]]

        roles: dict[str, dict[str, Any]] = {}
        role_warnings: list[str] = []
        for role, provider_id in sorted(self.asr_profile.roles.items()):
            enabled = provider_id is not None
            registered = bool(provider_id and provider_id in providers)
            roles[role] = {
                "provider": provider_id,
                "enabled": enabled,
                "registered": registered if enabled else None,
            }
            if enabled and not registered:
                role_warnings.append(
                    f"ASR role '{role}' references unregistered provider '{provider_id}'"
                )

        ffmpeg = _resolve_executable(self.config.ffmpeg_bin)
        ffprobe = _resolve_executable(self.config.ffprobe_bin)

        warnings = list(getattr(self, "startup_warnings", ()))
        warnings.extend(role_warnings)
        for provider_id, items in provider_preflight.items():
            for item in items:
                warnings.append(f"ASR provider '{provider_id}': {item}")
        if ffmpeg is None:
            warnings.append(f"ffmpeg not found: {self.config.ffmpeg_bin}")
        if ffprobe is None:
            warnings.append(f"ffprobe not found: {self.config.ffprobe_bin}")

        cleanup_registry = getattr(self, "cleanup_registry", None)
        cleanup_capabilities = cleanup_registry.capabilities() if cleanup_registry else ()
        cleanup_preflight = cleanup_registry.preflight() if cleanup_registry else {}
        for provider_id, items in cleanup_preflight.items():
            for item in items:
                warnings.append(f"cleanup provider '{provider_id}': {item}")

        return {
            "status": "ok" if not warnings else "degraded",
            "runtime_protocol": runtime_protocol(),
            "data_dir": str(self.config.paths.root),
            "tasks_dir": str(self.config.paths.tasks),
            "models_dir": str(self.config.paths.models),
            "media": {"ffmpeg": ffmpeg, "ffprobe": ffprobe},
            "asr": {
                "roles": roles,
                "providers": providers,
                "loaded_providers": loaded,
                "gpu_loaded": gpu_loaded,
                "multiple_gpu_resident": len(gpu_loaded) > 1,
                "gpu_residency_policy": "single_provider",
                "preflight": provider_preflight,
                "model_help": (
                    {"available": True, "tool": "asr_models",
                     "reason": "no ASR provider is currently registered"}
                    if not providers else None
                ),
            },
            "visual_cleanup": {
                "providers": cleanup_capabilities,
                "preflight": cleanup_preflight,
                "policy": "source-frame-first; generated pixels require explicit mask and provider",
            },
            "warnings": warnings,
            "models_loaded": bool(loaded),
        }


def _resolve_executable(value: str) -> str | None:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            return None
        return str(resolved) if resolved.is_file() else None
    found = shutil.which(value)
    return str(Path(found).resolve()) if found else None
