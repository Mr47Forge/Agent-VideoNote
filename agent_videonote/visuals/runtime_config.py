from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


VISUAL_RUNTIME_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VisualRuntimeConfig:
    schema_version: int = VISUAL_RUNTIME_SCHEMA_VERSION
    vsr_revision: str | None = None
    vsr_root: str | None = None
    lama_model: str | None = None
    sttn_model: str | None = None
    propainter_model_dir: str | None = None

    @classmethod
    def disabled(cls) -> "VisualRuntimeConfig":
        return cls()

    @classmethod
    def load(cls, path: Path) -> "VisualRuntimeConfig":
        if not path.is_file():
            return cls.disabled()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != VISUAL_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported visual runtime config schema")
        return cls(
            schema_version=VISUAL_RUNTIME_SCHEMA_VERSION,
            vsr_revision=_optional_string(payload.get("vsr_revision")),
            vsr_root=_optional_string(payload.get("vsr_root")),
            lama_model=_optional_string(payload.get("lama_model")),
            sttn_model=_optional_string(payload.get("sttn_model")),
            propainter_model_dir=_optional_string(payload.get("propainter_model_dir")),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)

    def resolved_paths(self) -> dict[str, Path | None]:
        result: dict[str, Path | None] = {}
        for name in ("vsr_root", "lama_model", "sttn_model", "propainter_model_dir"):
            value = getattr(self, name)
            result[name] = Path(value).expanduser().resolve() if value else None
        return result


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
