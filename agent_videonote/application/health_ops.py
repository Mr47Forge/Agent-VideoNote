from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


class HealthOperationsMixin:
    def health(self) -> dict[str, Any]:
        providers = self.asr_registry.list_capabilities()

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
        if ffmpeg is None:
            warnings.append(f"ffmpeg not found: {self.config.ffmpeg_bin}")
        if ffprobe is None:
            warnings.append(f"ffprobe not found: {self.config.ffprobe_bin}")

        return {
            "status": "ok" if not warnings else "degraded",
            "data_dir": str(self.config.paths.root),
            "tasks_dir": str(self.config.paths.tasks),
            "models_dir": str(self.config.paths.models),
            "media": {
                "ffmpeg": ffmpeg,
                "ffprobe": ffprobe,
            },
            "asr": {
                "roles": roles,
                "providers": providers,
            },
            "warnings": warnings,
            "models_loaded": False,
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
