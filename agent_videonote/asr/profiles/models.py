from __future__ import annotations

from dataclasses import dataclass

from agent_videonote.core.errors import ConfigurationError


@dataclass(frozen=True)
class AsrProfile:
    roles: dict[str, str | None]

    def provider_for(self, role: str) -> str | None:
        if role not in self.roles:
            raise ConfigurationError(f"ASR role not configured: {role}")
        return self.roles[role]

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "AsrProfile":
        raw_roles = data.get("roles")
        if not isinstance(raw_roles, dict):
            raise ConfigurationError("ASR profile must contain a roles object")
        roles: dict[str, str | None] = {}
        for key, value in raw_roles.items():
            if value is not None and not isinstance(value, str):
                raise ConfigurationError(f"invalid provider for role: {key}")
            roles[str(key)] = value
        return cls(roles=roles)
