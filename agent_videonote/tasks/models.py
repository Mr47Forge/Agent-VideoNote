from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_videonote.core.types import SourceIdentity


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TaskEvent:
    at: str
    type: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskState:
    schema_version: int
    task_id: str
    source: SourceIdentity
    current_stage: str
    completed_stages: list[str]
    artifacts: dict[str, dict[str, Any]]
    unresolved: list[dict[str, Any]]
    events: list[TaskEvent]
    created_at: str
    updated_at: str

    @classmethod
    def new(cls, task_id: str, source: SourceIdentity, initial_stage: str) -> "TaskState":
        now = utc_now()
        return cls(
            schema_version=1,
            task_id=task_id,
            source=source,
            current_stage=initial_stage,
            completed_stages=[],
            artifacts={},
            unresolved=[],
            events=[TaskEvent(at=now, type="task.created", detail={"stage": initial_stage})],
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        self.updated_at = utc_now()

    def add_event(self, event_type: str, detail: dict[str, Any] | None = None) -> None:
        self.events.append(TaskEvent(at=utc_now(), type=event_type, detail=detail or {}))
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskState":
        return cls(
            schema_version=int(data["schema_version"]),
            task_id=str(data["task_id"]),
            source=SourceIdentity(**data["source"]),
            current_stage=str(data["current_stage"]),
            completed_stages=[str(x) for x in data.get("completed_stages", [])],
            artifacts=dict(data.get("artifacts", {})),
            unresolved=list(data.get("unresolved", [])),
            events=[TaskEvent(**item) for item in data.get("events", [])],
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )
