from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_videonote.asr.context.service import ContextService
from agent_videonote.asr.request import RecognitionContext
from agent_videonote.storage.artifacts import write_json_atomic


@dataclass(frozen=True)
class CourseContext:
    course_id: str
    title_terms: tuple[str, ...] = ()
    glossary_terms: tuple[str, ...] = ()
    free_text: str | None = None
    language: str | None = None


class CourseContextRepository:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.builder = ContextService()

    def save(self, context: CourseContext) -> Path:
        if not context.course_id.strip():
            raise ValueError("course_id cannot be empty")
        return write_json_atomic(self.root / f"{_safe_id(context.course_id)}.json", asdict(context))

    def load(self, course_id: str) -> CourseContext:
        path = self.root / f"{_safe_id(course_id)}.json"
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return CourseContext(
            course_id=str(data["course_id"]),
            title_terms=tuple(data.get("title_terms", [])),
            glossary_terms=tuple(data.get("glossary_terms", [])),
            free_text=data.get("free_text"),
            language=data.get("language"),
        )

    def to_recognition_context(self, context: CourseContext) -> RecognitionContext:
        return self.builder.build(
            language=context.language,
            hotwords=(*context.title_terms, *context.glossary_terms),
            free_text=context.free_text,
        )


def _safe_id(value: str) -> str:
    cleaned = "".join(ch for ch in value.strip() if ch.isalnum() or ch in "-_")
    if not cleaned:
        raise ValueError("course_id contains no safe characters")
    return cleaned
