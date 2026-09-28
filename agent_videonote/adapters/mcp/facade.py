from __future__ import annotations

from typing import Any

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.request import RecognitionContext


class McpToolFacade:
    """Protocol-neutral tool surface to be bound to an MCP SDK later."""

    def __init__(self, application: ApplicationService):
        self.application = application

    def prepare(self, source: str) -> dict[str, Any]:
        return self.application.prepare(source)

    def ingest_srt(
        self,
        task_id: str,
        srt_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        return self.application.ingest_srt(task_id, srt_path, language=language)

    def transcribe(
        self,
        task_id: str,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        return self.application.transcribe(
            task_id,
            context=RecognitionContext(
                language=language,
                hotwords=tuple(hotwords or []),
                free_text=context_text,
            ),
        )

    def review(
        self,
        task_id: str,
        start: float,
        end: float,
        speed: float = 1.0,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        return self.application.review(
            task_id,
            start=start,
            end=end,
            speed=speed,
            context=RecognitionContext(
                language=language,
                hotwords=tuple(hotwords or []),
                free_text=context_text,
            ),
        )

    def task(self, task_id: str) -> dict[str, Any]:
        return self.application.get_task(task_id)

    def complete_visual(self, task_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return self.application.complete_visual(task_id, evidence)

    def validate_delivery(self, task_id: str, deliverables_dir: str) -> dict[str, Any]:
        report = self.application.validate_and_finish_delivery(task_id, deliverables_dir)
        return {
            "ok": report.ok,
            "problems": list(report.problems),
            "image_references": list(report.image_references),
        }
