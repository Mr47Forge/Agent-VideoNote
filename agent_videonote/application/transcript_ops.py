from __future__ import annotations

import hashlib
import json
import time
import traceback
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.context.repository import CourseContext
from agent_videonote.asr.request import RecognitionContext, TranscriptionRequest
from agent_videonote.core.errors import CapabilityError, ConfigurationError, InvalidTransitionError
from agent_videonote.core.types import Artifact, TimeRange
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.transcripts.srt import load_srt
from agent_videonote.transcripts.types import (
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from agent_videonote.transcripts.validation import validate_transcript
from agent_videonote.workflow.stages import WorkflowStage


_MAX_TRANSCRIPT_SEGMENTS_PER_READ = 200
_MAX_REVIEW_SECONDS = 180.0


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
        started = time.perf_counter()
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        orphan_transcript = self.task_dir(task_id) / "transcript" / "transcript.json"
        if not existing and orphan_transcript.is_file():
            _validate_persisted_transcript(orphan_transcript)
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
                    expected_stage=WorkflowStage.TRANSCRIPT,
                    evidence={
                        "transcript": str(path),
                        "source_id": summary.get("source_id"),
                        "recovered": True,
                    },
                )
            summary["task"] = self._task_summary(self.tasks.get(task_id))
            summary["reused"] = True
            summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
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
            expected_stage=WorkflowStage.TRANSCRIPT,
            evidence={"transcript": str(path), "source_id": transcript.source_id},
        )
        summary = self._transcript_summary(task_id, path)
        summary["task"] = self._task_summary(self.tasks.get(task_id))
        summary["reused"] = False
        summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return summary

    def transcribe(
        self,
        task_id: str,
        *,
        context: RecognitionContext | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        orphan_transcript = self.task_dir(task_id) / "transcript" / "transcript.json"
        if not existing and orphan_transcript.is_file():
            _validate_persisted_transcript(orphan_transcript)
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
                    expected_stage=WorkflowStage.TRANSCRIPT,
                    evidence={
                        "transcript": str(path),
                        "source_id": summary.get("source_id"),
                        "recovered": True,
                    },
                )
            summary["task"] = self._task_summary(self.tasks.get(task_id))
            summary["reused"] = True
            summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
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
        gpu_guard = (
            self._gpu_operation_lock
            if AsrCapability.GPU in provider.capabilities
            else nullcontext()
        )

        with gpu_guard:
            try:
                audio_path = self.task_dir(task_id) / "source" / "audio.wav"
                if not audio_path.is_file():
                    self.media.extract_audio(state.source.path, audio_path)

                transcript = provider.transcribe(
                    TranscriptionRequest(audio_path=audio_path, context=ctx)
                )
                problems = validate_transcript(transcript)
                if problems:
                    raise CapabilityError(
                        "invalid provider transcript: " + "; ".join(problems)
                    )

                path = self._save_transcript(task_id, transcript)
                if read_json(path) != json.loads(
                    json.dumps(transcript.to_dict(), ensure_ascii=False)
                ):
                    raise CapabilityError(
                        "persisted provider transcript does not match validated result"
                    )
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
                    expected_stage=WorkflowStage.TRANSCRIPT,
                    evidence={
                        "transcript": str(path),
                        "source_id": transcript.source_id,
                    },
                )
                summary = self._transcript_summary(task_id, path)
                summary["task"] = self._task_summary(self.tasks.get(task_id))
                summary["reused"] = False
                summary["elapsed_seconds"] = round(
                    time.perf_counter() - started, 3
                )
                return summary
            except BaseException as error:
                # Finished inference frames can retain the GPU model through locals.
                traceback.clear_frames(error.__traceback__)
                raise
            finally:
                self.asr_registry.release_provider(provider_id)

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

        if not 0.5 <= speed <= 2.0:
            raise ValueError("review speed must be between 0.5 and 2.0")
        window = TimeRange(start=start, end=end)
        if window.duration > _MAX_REVIEW_SECONDS:
            raise ValueError(
                f"review window cannot exceed {_MAX_REVIEW_SECONDS:.0f} seconds"
            )
        media_duration = _task_media_duration(self, state)
        if media_duration is not None and end > media_duration + 0.001:
            raise ValueError(
                f"review window ends after source duration: "
                f"{end:.3f} > {media_duration:.3f}"
            )

        ctx = self._resolve_context(context=context, course_id=course_id)
        required = {AsrCapability.SHORT_AUDIO} | _context_capabilities(ctx)
        provider = self.asr_registry.get(provider_id, required)

        token = _review_cache_token(
            start=start,
            end=end,
            speed=speed,
            provider_id=provider_id,
            course_id=course_id,
            context=ctx,
        )
        review_path = self.task_dir(task_id) / "reviews" / "results" / f"{token}.json"
        if review_path.is_file():
            _validate_persisted_transcript(review_path)
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

        gpu_guard = (
            self._gpu_operation_lock
            if AsrCapability.GPU in provider.capabilities
            else nullcontext()
        )
        with gpu_guard:
            try:
                transcript = provider.transcribe(
                    TranscriptionRequest(
                        audio_path=audio_path,
                        context=ctx,
                        source_range=window,
                    )
                )
                transcript = _restore_review_timeline(
                    transcript,
                    window=window,
                    speed=speed,
                )
                problems = validate_transcript(transcript)
                if problems:
                    raise CapabilityError(
                        "invalid review transcript: " + "; ".join(problems)
                    )
            except BaseException as error:
                traceback.clear_frames(error.__traceback__)
                self.asr_registry.release_provider(provider_id)
                raise
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
    course_id: str | None,
    context: RecognitionContext,
) -> str:
    payload = json.dumps(
        {
            "start": start,
            "end": end,
            "speed": speed,
            "provider_id": provider_id,
            "course_id": course_id,
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



def _validate_persisted_transcript(path: Path) -> None:
    """Reject a semantically incomplete persisted transcript before reuse."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise CapabilityError("recovered transcript payload must be an object")
    source_id = payload.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise CapabilityError("recovered transcript is missing source_id")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise CapabilityError("recovered transcript segments must be a list")
    try:
        segments = tuple(
            TranscriptSegment(
                start=float(item["start"]),
                end=float(item["end"]),
                text=str(item["text"]),
            )
            for item in raw_segments
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CapabilityError("recovered transcript has invalid segment fields") from exc

    recovered = Transcript(
        text=str(payload.get("text") or ""),
        segments=segments,
        source_id=source_id,
        language=(
            str(payload["language"])
            if payload.get("language") is not None
            else None
        ),
    )
    problems = validate_transcript(recovered)
    if problems:
        raise CapabilityError(
            "invalid recovered transcript: " + "; ".join(problems)
        )


def _task_media_duration(service: Any, state: Any) -> float | None:
    artifact = state.artifacts.get("media_info")
    if artifact and Path(artifact["path"]).is_file():
        payload = read_json(artifact["path"])
        value = payload.get("duration")
        if value is not None:
            try:
                duration = float(value)
            except (TypeError, ValueError):
                duration = None
            if duration is not None and duration > 0:
                return duration

    info = service.media.probe(state.source.path)
    return float(info.duration) if info.duration is not None else None


def _restore_review_timeline(
    transcript: Transcript,
    *,
    window: TimeRange,
    speed: float,
) -> Transcript:
    """Map timestamps from speed-adjusted review audio back to source-video time."""
    if abs(speed - 1.0) < 1e-9 or not transcript.segments:
        return transcript

    # Providers without detailed timestamps deliberately use the original
    # source_range as one fallback segment; that range is already correct.
    if (
        len(transcript.segments) == 1
        and not transcript.segments[0].words
        and abs(transcript.segments[0].start - window.start) <= 0.001
        and abs(transcript.segments[0].end - window.end) <= 0.001
    ):
        return transcript

    def scale(second: float) -> float:
        mapped = window.start + (float(second) - window.start) * speed
        return min(window.end, max(window.start, mapped))

    segments: list[TranscriptSegment] = []
    for segment in transcript.segments:
        words = tuple(
            TranscriptWord(
                start=scale(word.start),
                end=scale(word.end),
                text=word.text,
            )
            for word in segment.words
        )
        segments.append(
            TranscriptSegment(
                start=scale(segment.start),
                end=scale(segment.end),
                text=segment.text,
                words=words,
            )
        )

    return Transcript(
        text=transcript.text,
        segments=tuple(segments),
        source_id=transcript.source_id,
        language=transcript.language,
        metadata=dict(transcript.metadata),
    )
