from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.profiles.models import AsrProfile
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.asr.request import RecognitionContext, TranscriptionRequest
from agent_videonote.core.config import RuntimeConfig
from agent_videonote.core.errors import CapabilityError, ConfigurationError, InvalidTransitionError
from agent_videonote.core.types import Artifact, TimeRange
from agent_videonote.delivery.validator import DeliveryReport, validate_delivery
from agent_videonote.media.interfaces import MediaBackend
from agent_videonote.storage.artifacts import read_json, write_json_atomic
from agent_videonote.tasks.service import TaskService
from agent_videonote.transcripts.srt import load_srt
from agent_videonote.transcripts.types import Transcript
from agent_videonote.transcripts.validation import validate_transcript
from agent_videonote.workflow.engine import WorkflowEngine
from agent_videonote.workflow.stages import WorkflowStage


class ApplicationService:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        tasks: TaskService,
        workflow: WorkflowEngine,
        media: MediaBackend,
        asr_registry: ProviderRegistry,
        asr_profile: AsrProfile,
    ):
        self.config = config
        self.tasks = tasks
        self.workflow = workflow
        self.media = media
        self.asr_registry = asr_registry
        self.asr_profile = asr_profile

    def task_dir(self, task_id: str) -> Path:
        return self.config.paths.tasks / task_id

    def prepare(self, source: str | Path) -> dict[str, Any]:
        state = self.tasks.create_or_resume(source)
        existing = state.artifacts.get("media_info")
        if existing and Path(existing["path"]).is_file():
            return {"task": self._task_summary(state), "media": read_json(existing["path"])}

        info = self.media.probe(state.source.path)
        media_path = write_json_atomic(
            self.task_dir(state.task_id) / "source" / "media.json",
            asdict(info),
        )
        state = self.tasks.register_artifact(
            state.task_id,
            "media_info",
            Artifact(kind="media_info", path=str(media_path)),
        )

        if state.current_stage == WorkflowStage.INPUT.value:
            state = self.workflow.complete_current(
                state.task_id,
                evidence={"source": state.source.path, "media_info": str(media_path)},
            )

        return {"task": self._task_summary(state), "media": asdict(info)}

    def ingest_srt(
        self,
        task_id: str,
        srt_path: str | Path,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        if existing and Path(existing["path"]).is_file():
            return read_json(existing["path"])

        if state.current_stage != WorkflowStage.TRANSCRIPT.value:
            raise InvalidTransitionError("task is not in transcript stage")

        transcript = load_srt(srt_path, language=language)
        path = self._save_transcript(task_id, transcript)
        self.tasks.register_artifact(
            task_id,
            "transcript",
            Artifact(kind="transcript", path=str(path), metadata={"source": "srt"}),
        )
        self.workflow.complete_current(
            task_id,
            evidence={"transcript": str(path), "source_id": transcript.source_id},
        )
        return transcript.to_dict()

    def transcribe(
        self,
        task_id: str,
        *,
        context: RecognitionContext | None = None,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        existing = state.artifacts.get("transcript")
        if existing and Path(existing["path"]).is_file():
            return read_json(existing["path"])

        if state.current_stage != WorkflowStage.TRANSCRIPT.value:
            raise InvalidTransitionError("task is not in transcript stage")

        provider_id = self.asr_profile.provider_for("primary")
        if provider_id is None:
            raise ConfigurationError("primary ASR role is disabled")

        ctx = context or RecognitionContext()
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
                metadata={"source_id": transcript.source_id},
            ),
        )
        self.workflow.complete_current(
            task_id,
            evidence={"transcript": str(path), "source_id": transcript.source_id},
        )
        return transcript.to_dict()

    def review(
        self,
        task_id: str,
        *,
        start: float,
        end: float,
        context: RecognitionContext | None = None,
        speed: float = 1.0,
    ) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        provider_id = self.asr_profile.provider_for("review")
        if provider_id is None:
            raise ConfigurationError("review ASR role is disabled")

        window = TimeRange(start=start, end=end)
        ctx = context or RecognitionContext()
        required = {AsrCapability.SHORT_AUDIO} | _context_capabilities(ctx)
        provider = self.asr_registry.get(provider_id, required)

        token = f"{start:.3f}-{end:.3f}-x{speed:.2f}".replace(".", "_")
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

        review_path = write_json_atomic(
            self.task_dir(task_id) / "reviews" / "results" / f"{token}.json",
            result,
        )
        self.tasks.register_artifact(
            task_id,
            f"review:{token}",
            Artifact(
                kind="asr_review",
                path=str(review_path),
                metadata={"source_id": transcript.source_id, "start": start, "end": end},
            ),
        )
        return result

    def complete_visual(self, task_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        state = self.tasks.get(task_id)
        if state.current_stage != WorkflowStage.VISUAL.value:
            raise InvalidTransitionError("task is not in visual stage")
        state = self.workflow.complete_current(task_id, evidence=evidence)
        return self._task_summary(state)

    def validate_and_finish_delivery(
        self,
        task_id: str,
        deliverables_dir: str | Path,
    ) -> DeliveryReport:
        state = self.tasks.get(task_id)
        if state.current_stage != WorkflowStage.DELIVERY.value:
            raise InvalidTransitionError("task is not in delivery stage")

        report = validate_delivery(deliverables_dir)
        report_path = write_json_atomic(
            self.task_dir(task_id) / "delivery" / "report.json",
            {
                "ok": report.ok,
                "problems": list(report.problems),
                "image_references": list(report.image_references),
                "deliverables_dir": str(Path(deliverables_dir).resolve()),
            },
        )
        self.tasks.register_artifact(
            task_id,
            "delivery_report",
            Artifact(kind="delivery_report", path=str(report_path)),
        )

        if report.ok:
            self.workflow.complete_current(
                task_id,
                evidence={"delivery_report": str(report_path)},
            )
            self.workflow.mark_done(task_id, evidence={"validated": True})
        return report

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._task_summary(self.tasks.get(task_id))

    def _save_transcript(self, task_id: str, transcript: Transcript) -> Path:
        return write_json_atomic(
            self.task_dir(task_id) / "transcript" / "transcript.json",
            transcript.to_dict(),
        )

    @staticmethod
    def _task_summary(state: Any) -> dict[str, Any]:
        return {
            "task_id": state.task_id,
            "source": state.source.path,
            "current_stage": state.current_stage,
            "completed_stages": list(state.completed_stages),
            "artifacts": dict(state.artifacts),
            "unresolved_count": len(state.unresolved),
            "updated_at": state.updated_at,
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
