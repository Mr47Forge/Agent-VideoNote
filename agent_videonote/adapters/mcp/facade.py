from __future__ import annotations

from typing import Any

from agent_videonote.application.service import ApplicationService
from agent_videonote.asr.request import RecognitionContext


class McpToolFacade:
    """Protocol-neutral tool surface to be bound to an MCP SDK."""

    def __init__(self, application: ApplicationService):
        self.application = application

    def health(self) -> dict[str, Any]:
        return self.application.health()

    def release_asr_role(self, role: str) -> dict[str, Any]:
        return self.application.release_role(role)

    def asr_setup_plan(self, search_dirs: list[str] | None = None) -> dict[str, Any]:
        return self.application.asr_setup_plan(search_dirs=search_dirs)

    def visual_setup(self, apply: bool = False) -> dict[str, Any]:
        return self.application.visual_setup(apply=apply)

    def asr_models(
        self,
        role: str | None = None,
        priority: str = "balanced",
        integrated_only: bool = False,
        limit: int = 5,
        detail: str = "compact",
    ) -> dict[str, Any]:
        return self.application.list_asr_models(
            role=role,
            priority=priority,
            integrated_only=integrated_only,
            limit=limit,
            detail=detail,
        )

    def prepare(self, source: str) -> dict[str, Any]:
        return self.application.prepare(source)

    def set_course_context(
        self,
        course_id: str,
        title_terms: list[str] | None = None,
        glossary_terms: list[str] | None = None,
        free_text: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        return self.application.set_course_context(
            course_id=course_id,
            title_terms=title_terms or [],
            glossary_terms=glossary_terms or [],
            free_text=free_text,
            language=language,
        )

    def get_course_context(self, course_id: str) -> dict[str, Any]:
        return self.application.get_course_context(course_id)

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
        course_id: str | None = None,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        return self.application.transcribe(
            task_id,
            course_id=course_id,
            context=_explicit_context(language, hotwords, context_text),
        )

    def get_transcript(
        self,
        task_id: str,
        start_segment: int = 1,
        end_segment: int = 80,
        include_words: bool = False,
    ) -> dict[str, Any]:
        return self.application.get_transcript(
            task_id,
            start_segment=start_segment,
            end_segment=end_segment,
            include_words=include_words,
        )

    def review(
        self,
        task_id: str,
        start: float,
        end: float,
        speed: float = 1.0,
        course_id: str | None = None,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        return self.application.review(
            task_id,
            start=start,
            end=end,
            speed=speed,
            course_id=course_id,
            context=_explicit_context(language, hotwords, context_text),
        )

    def task(self, task_id: str) -> dict[str, Any]:
        return self.application.get_task(task_id)

    def task_context(self, task_id: str) -> dict[str, Any]:
        return self.application.get_task_context(task_id)

    def discover_visuals(self, task_id: str, budget_seconds: float = 120.0,
                         config: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.application.discover_visuals(
            task_id, budget_seconds=budget_seconds, config=config,
        )

    def get_visual_candidates(self, task_id: str, start: int = 0,
                              limit: int = 20) -> dict[str, Any]:
        return self.application.get_visual_candidates(task_id, start=start, limit=limit)

    def clean_visual_candidate(self, task_id: str, candidate_id: str) -> dict[str, Any]:
        return self.application.clean_visual_candidate(task_id, candidate_id)

    def repair_visual_candidate(
        self,
        task_id: str,
        candidate_id: str,
        provider: str,
        mask_path: str,
        window_seconds: float = 3.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        return self.application.repair_visual_candidate(
            task_id,
            candidate_id,
            provider=provider,
            mask_path=mask_path,
            window_seconds=window_seconds,
            interval=interval,
        )

    def complete_visual(self, task_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"task": self.application.complete_visual(task_id, evidence)}

    def validate_delivery(self, task_id: str, deliverables_dir: str) -> dict[str, Any]:
        report = self.application.validate_and_finish_delivery(task_id, deliverables_dir)
        return {
            "ok": report.ok,
            "problems": list(report.problems),
            "image_references": list(report.image_references),
            "orphan_images": list(report.orphan_images),
            "unexpected_entries": list(report.unexpected_entries),
            "task": self.application.get_task(task_id),
        }


def _explicit_context(
    language: str | None,
    hotwords: list[str] | None,
    context_text: str | None,
) -> RecognitionContext | None:
    if not language and not hotwords and not context_text:
        return None
    return RecognitionContext(
        language=language,
        hotwords=tuple(hotwords or []),
        free_text=context_text,
    )
