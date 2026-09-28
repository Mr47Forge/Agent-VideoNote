from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Benchmark:
    dataset: str
    metric: str
    value: float
    unit: str
    note: str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelCard:
    catalog_id: str
    name: str
    model_id: str
    provider_driver: str | None
    integration_status: str
    fit_roles: tuple[str, ...]
    languages: str
    speed: str
    quality: str
    hardware_note: str
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    capabilities: tuple[str, ...]
    benchmarks: tuple[Benchmark, ...]
    license_note: str
    verified_at: str
    source: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["benchmarks"] = [item.to_dict() for item in self.benchmarks]
        return data
