from __future__ import annotations

from collections.abc import Iterable

from agent_videonote.asr.request import RecognitionContext


class ContextService:
    def build(
        self,
        *,
        language: str | None = None,
        hotwords: Iterable[str] = (),
        free_text: str | None = None,
        max_hotwords: int = 500,
    ) -> RecognitionContext:
        if max_hotwords < 1:
            raise ValueError("max_hotwords must be positive")

        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in hotwords:
            term = str(raw).strip()
            if not term or term in seen:
                continue
            seen.add(term)
            cleaned.append(term)
            if len(cleaned) >= max_hotwords:
                break

        text = free_text.strip() if free_text and free_text.strip() else None
        return RecognitionContext(
            language=language.strip() if language and language.strip() else None,
            hotwords=tuple(cleaned),
            free_text=text,
        )
