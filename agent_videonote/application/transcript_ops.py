from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.context.repository import CourseContext
from agent_videonote.asr.request import RecognitionContext, TranscriptionRequest
from agent_videonote.core.errors import CapabilityError, ConfigurationError, InvalidTransitionError
from agent_videonote.core.types import Artifact, TimeRange
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.transcripts.srt import load_srt
from agent_videonote.transcripts.types import Transcript
from agent_videonote.transcripts.validation import validate_transcript
from agent_videonote.workflow.stages import WorkflowStage


_MAX_TRANSCRIPT_SEGMENTS_PER_READ = 200


class TranscriptOperationsMixin:
    def set_course_context(
        self,
        *,
        course_id: str,
        title_terms: list[str] | tuple[str, ...] = (),
        glossary_terms: list[str] | tuple[str, ...] = (),
        free_text: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        context = CourseContext(
            course_id=course_id,
            title_terms=tuple(_clean_terms(title_terms)),
            glossary_terms=tuple(_clean_terms(glossary_terms)),
            free_text=free_text.strip() if free_text and free_text.strip() else None,
            language=language.strip() if language and language.strip() else None,
        )
        path = self.contexts.save(context)
        return {
            "course_id": context.course_id,
            "title_terms": list(context.title_terms),
            "glossary_terms": list(context.glossary_terms),
            "free_text": context.free_text,
            "language": context.language,
            "path": str(path),
        }

    def get_course_context(self, course_id: str) -> dict[str, Any]:
        context = self.contexts.load(course_id)
        return {
            "course_id": context.course_id,
            "title_terms": list(context.title_terms),
            "glossary_terms": list(context.glossary_terms),
            "free_text": context.free_text,
            "language": context.language,
        }

    def ingest_srt(
        self,
        task_id: str,
        srt_path: str | Path,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        orphan_transcript = self.task_dir(task_id) / "transcript" / "transcript.json"
        if not existing and orphan_transcript.is_file():
            summary = self._transcript_summary(task_id, orphan_transcript)
            state = self.tasks.register_artifact(
                task_id,
                "transcript",
                Artifact(
                    kind="transcript",
                    path=str(orphan_transcript),
                    metadata={"source_id": summary.get("source_id"), "recovered": True},
                ),
            )
            existing = state.artifacts.get("transcript")
        if existing and Path(existing["path"]).is_file():
            path = Path(existing["path"])
            summary = self._transcript_summary(task_id, path)
            if state.current_stage == WorkflowStage.TRANSCRIPT.value:
                self.workflow.complete_current(
                    task_id,
                    evidence={
                        "transcript": str(path),
                        "source_id": summary.get("source_id"),
                        "recovered": True,
                    },
                )
            return summary

        if state.current_stage != WorkflowStage.TRANSCRIPT.value:
            raise InvalidTransitionError("task is not in transcript stage")

        transcript = load_srt(srt_path, language=language)
        problems = validate_transcript(transcript)
        if problems:
            raise CapabilityError("invalid SRT transcript: " + "; ".join(problems))

        path = self._save_transcript(task_id, transcript)
        self.tasks.register_artifact(
            task_id,
            "transcript",
            Artifact(
                kind="transcript",
                path=str(path),
                metadata={"source_id": transcript.source_id},
            ),
        )
        self.workflow.complete_current(
            task_id,
            evidence={"transcript": str(path), "source_id": transcript.source_id},
        )
        return self._transcript_summary(task_id, path)

    def transcribe(
        self,
        task_id: str,
        *,
        context: RecognitionContext | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        orphan_transcript = self.task_dir(task_id) / "transcript" / "transcript.json"
        if not existing and orphan_transcript.is_file():
            summary = self._transcript_summary(task_id, orphan_transcript)
            state = self.tasks.register_artifact(
                task_id,
                "transcript",
                Artifact(
                    kind="transcript",
                    path=str(orphan_transcript),
                    metadata={"source_id": summary.get("source_id"), "recovered": True},
                ),
            )
            existing = state.artifacts.get("transcript")
        if existing and Path(existing["path"]).is_file():
            path = Path(existing["path"])
            summary = self._transcript_summary(task_id, path)
            if state.current_stage == WorkflowStage.TRANSCRIPT.value:
                self.workflow.complete_current(
                    task_id,
                    evidence={
                        "transcript": str(path),
                        "source_id": summary.get("source_id"),
                        "recovered": True,
                    },
                )
            return summary

        if state.current_stage != WorkflowStage.TRANSCRIPT.value:
            raise InvalidTransitionError("task is not in transcript stage")

        provider_id = self.asr_profile.provider_for("primary")
        if provider_id is None:
            raise ConfigurationError("primary ASR role is disabled")

        ctx = self._resolve_context(context=context, course_id=course_id)
        required = {
            AsrCapability.LONG_AUDIO,
            AsrCapability.SEGMENT_TIMESTAMPS,
        }
        required |= _context_capabilities(ctx)
        provider = self.asr_registry.get(provider_id, required)

        audio_path = self.task_dir(task_id) / "source" / "audio.wav"
        if not audio_path.is_file():
            self.media.extract_audio(state.source.path, audio_path)

        transcript = provider.transcribe(
            TranscriptionRequest(audio_path=audio_path, context=ctx)
        )
        problems = validate_transcript(transcript)
        if problems:
            raise CapabilityError("invalid provider transcript: " + "; ".join(problems))

        path = self._save_transcript(task_id, transcript)
        self.tasks.register_artifact(
            task_id,
            "transcript",
            Artifact(
                kind="transcript",
                path=str(path),
                metadata={
                    "source_id": transcript.source_id,
                    "course_id": course_id,
                },
            ),
        )
        self.workflow.complete_current(
            task_id,
            evidence={"transcript": str(path), "source_id": transcript.source_id},
        )
        return self._transcript_summary(task_id, path)

    def get_transcript(
        self,
        task_id: str,
        *,
        start_segment: int = 1,
        end_segment: int = 80,
        include_words: bool = False,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        artifact = state.artifacts.get("transcript")
        if not artifact:
            raise FileNotFoundError("task has no transcript artifact")

        path = Path(artifact["path"])
        if not path.is_file():
            raise FileNotFoundError(path)

        payload = read_json(path)
        segments = payload.get("segments") or []
        total = len(segments)
        if total == 0:
            return {
                "task_id": task_id,
                "source_id": payload.get("source_id"),
                "total": 0,
                "start": 0,
                "end": 0,
                "segments": [],
            }

        if start_segment < 1:
            raise ValueError("start_segment must be >= 1")
        if end_segment < start_segment:
            raise ValueError("end_segment must be >= start_segment")
        if end_segment - start_segment + 1 > _MAX_TRANSCRIPT_SEGMENTS_PER_READ:
            raise ValueError(
                f"one read may contain at most {_MAX_TRANSCRIPT_SEGMENTS_PER_READ} segments"
            )

        start = min(start_segment, total)
        end = min(end_segment, total)
        selected: list[dict[str, Any]] = []
        for index in range(start - 1, end):
            item = dict(segments[index])
            if not include_words:
                item.pop("words", None)
            selected.append({"n": index + 1, **item})

        return {
            "task_id": task_id,
            "source_id": payload.get("source_id"),
            "language": payload.get("language"),
            "total": total,
            "start": start,
            "end": end,
            "has_more": end < total,
            "next_start": end + 1 if end < total else None,
            "segments": selected,
        }

    def review(
        self,
        task_id: str,
        *,
        start: float,
        end: float,
        context: RecognitionContext | None = None,
        course_id: str | None = None,
        speed: float = 1.0,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        provider_id = self.asr_profile.provider_for("review")
        if provider_id is None:
            raise ConfigurationError("review ASR role is disabled")

        window = TimeRange(start=start, end=end)
        ctx = self._resolve_context(context=context, course_id=course_id)
        required = {AsrCapability.SHORT_AUDIO} | _context_capabilities(ctx)
        provider = self.asr_registry.get(provider_id, required)

        token = _review_cache_token(
            start=start,
            end=end,
            speed=speed,
            provider_id=provider_id,
            context=ctx,
        )
        review_path = self.task_dir(task_id) / "reviews" / "results" / f"{token}.json"
        if review_path.is_file():
            result = read_json(review_path)
            artifact_name = f"review:{token}"
            if artifact_name not in state.artifacts:
                self.tasks.register_artifact(
                    task_id,
                    artifact_name,
                    Artifact(
                        kind="asr_review",
                        path=str(review_path),
                        metadata={
                            "source_id": result.get("source_id"),
                            "start": start,
                            "end": end,
                            "course_id": course_id,
                            "recovered": True,
                        },
                    ),
                )
            return result

        audio_path = self.task_dir(task_id) / "reviews" / "audio" / f"{token}.wav"
        if not audio_path.is_file():
            self.media.cut_audio(
                state.source.path,
                audio_path,
                start=start,
                duration=window.duration,
                speed=speed,
            )

        transcript = provider.transcribe(
            TranscriptionRequest(
                audio_path=audio_path,
                context=ctx,
                source_range=window,
            )
        )
        result = transcript.to_dict()
        result["source_range"] = {"start": start, "end": end}
        result["speed"] = speed
        result["course_id"] = course_id

        write_json_atomic(review_path, result)
        self.tasks.register_artifact(
            task_id,
            f"review:{token}",
            Artifact(
                kind="asr_review",
                path=str(review_path),
                metadata={
                    "source_id": transcript.source_id,
                    "start": start,
                    "end": end,
                    "course_id": course_id,
                },
            ),
        )
        # Return the persisted JSON shape so cache-hit and cache-miss responses
        # have identical list/dict types.
        return read_json(review_path)

    def _resolve_context(
        self,
        *,
        context: RecognitionContext | None,
        course_id: str | None,
    ) -> RecognitionContext:
        base = (
            self.contexts.to_recognition_context(self.contexts.load(course_id))
            if course_id is not None
            else RecognitionContext()
        )
        if context is None:
            return base

        return _merge_recognition_context(base, context)

    def _save_transcript(self, task_id: str, transcript: Transcript) -> Path:
        return write_json_atomic(
            self.task_dir(task_id) / "transcript" / "transcript.json",
            transcript.to_dict(),
        )

    def _transcript_summary(self, task_id: str, path: Path) -> dict[str, Any]:
        payload = read_json(path)
        return {
            "task_id": task_id,
            "path": str(path),
            "source_id": payload.get("source_id"),
            "language": payload.get("language"),
            "segments": len(payload.get("segments") or []),
            "characters": len(str(payload.get("text") or "")),
            "read_with": "get_transcript",
        }


def _context_capabilities(context: RecognitionContext) -> set[AsrCapability]:
    required: set[AsrCapability] = set()
    if context.hotwords:
        required.add(AsrCapability.HOTWORDS)
    if context.free_text:
        required.add(AsrCapability.FREE_CONTEXT)
    if context.language:
        required.add(AsrCapability.EXPLICIT_LANGUAGE)
    return required


def _clean_terms(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        term = str(raw).strip()
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result

def _merge_recognition_context(
    base: RecognitionContext,
    override: RecognitionContext,
) -> RecognitionContext:
    hotwords = tuple(_clean_terms((*base.hotwords, *override.hotwords)))

    texts: list[str] = []
    for value in (base.free_text, override.free_text):
        if value and value.strip() and value.strip() not in texts:
            texts.append(value.strip())

    return RecognitionContext(
        language=override.language or base.language,
        hotwords=hotwords,
        free_text="\n".join(texts) if texts else None,
    )

def _review_cache_token(
    *,
    start: float,
    end: float,
    speed: float,
    provider_id: str,
    context: RecognitionContext,
) -> str:
    payload = json.dumps(
        {
            "provider_id": provider_id,
            "language": context.language,
            "hotwords": list(context.hotwords),
            "free_text": context.free_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:12]
    prefix = f"{start:.3f}-{end:.3f}-x{speed:.2f}".replace(".", "_")
    return f"{prefix}-{digest}"

