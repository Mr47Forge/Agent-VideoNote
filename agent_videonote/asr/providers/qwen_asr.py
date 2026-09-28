from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.request import TranscriptionRequest
from agent_videonote.core.errors import CapabilityError, ConfigurationError
from agent_videonote.transcripts.types import Transcript, TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class QwenAsrConfig:
    provider_id: str
    model: str
    device_map: str = "cuda:0"
    dtype: str = "bfloat16"
    max_inference_batch_size: int = 1
    max_new_tokens: int = 256
    forced_aligner: str | None = None
    forced_aligner_device_map: str | None = None
    supports_long_audio: bool = False
    extra_init: dict[str, Any] = field(default_factory=dict)


class QwenAsrProvider:
    """Generic Qwen3-ASR provider using the upstream qwen-asr package."""

    def __init__(self, config: QwenAsrConfig):
        if not config.provider_id.strip():
            raise ConfigurationError("provider_id cannot be empty")
        if not config.model.strip():
            raise ConfigurationError("Qwen ASR model cannot be empty")
        self.config = config
        self._model: Any | None = None

    @property
    def provider_id(self) -> str:
        return self.config.provider_id

    @property
    def capabilities(self) -> frozenset[AsrCapability]:
        caps = {
            AsrCapability.SHORT_AUDIO,
            AsrCapability.HOTWORDS,
            AsrCapability.FREE_CONTEXT,
            AsrCapability.EXPLICIT_LANGUAGE,
            AsrCapability.PERSISTENT_INSTANCE,
            AsrCapability.LOCAL,
        }
        if self.config.supports_long_audio:
            caps.add(AsrCapability.LONG_AUDIO)
        if self.config.forced_aligner:
            caps.add(AsrCapability.WORD_TIMESTAMPS)
            caps.add(AsrCapability.SEGMENT_TIMESTAMPS)
        if "cuda" in self.config.device_map.lower():
            caps.add(AsrCapability.GPU)
        return frozenset(caps)

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        model = self._ensure_model()
        context_text = _build_context(
            request.context.free_text,
            request.context.hotwords,
        )

        results = model.transcribe(
            audio=str(request.audio_path),
            context=context_text,
            language=request.context.language,
            return_time_stamps=bool(self.config.forced_aligner),
        )
        if not isinstance(results, list) or not results:
            raise CapabilityError(f"{self.provider_id} returned no transcription result")

        result = results[0]
        text = str(getattr(result, "text", "") or "").strip()
        language = str(getattr(result, "language", "") or "").strip() or request.context.language
        offset = request.source_range.start if request.source_range else 0.0

        words: list[TranscriptWord] = []
        raw_timestamps = getattr(result, "time_stamps", None)
        if raw_timestamps:
            for item in raw_timestamps:
                token = str(getattr(item, "text", "") or "")
                start = getattr(item, "start_time", None)
                end = getattr(item, "end_time", None)
                if token and _is_number(start) and _is_number(end) and float(end) > float(start):
                    words.append(
                        TranscriptWord(
                            start=float(start) + offset,
                            end=float(end) + offset,
                            text=token,
                        )
                    )

        segments = _segments_from_words(words)
        if self.config.forced_aligner and not segments:
            raise CapabilityError(
                f"{self.provider_id} was configured with a forced aligner, "
                "but returned no timestamps"
            )

        if not segments and text:
            start, end = _fallback_range(request)
            segments = [TranscriptSegment(start=start, end=end, text=text)]

        return Transcript(
            text=text,
            segments=tuple(segments),
            source_id=f"asr:{self.provider_id}",
            language=language,
            metadata={
                "framework": "qwen-asr",
                "model": self.config.model,
                "forced_aligner": self.config.forced_aligner,
            },
        )

    def close(self) -> None:
        self._model = None
        try:
            import torch
            if "cuda" in self.config.device_map.lower() and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise ConfigurationError(
                "Qwen ASR provider requires the upstream 'qwen-asr' package and PyTorch"
            ) from exc

        dtype = getattr(torch, self.config.dtype, None)
        if dtype is None:
            raise ConfigurationError(f"unknown torch dtype: {self.config.dtype}")

        kwargs: dict[str, Any] = {
            "dtype": dtype,
            "device_map": self.config.device_map,
            "max_inference_batch_size": self.config.max_inference_batch_size,
            "max_new_tokens": self.config.max_new_tokens,
            **self.config.extra_init,
        }
        if self.config.forced_aligner:
            kwargs["forced_aligner"] = self.config.forced_aligner
            kwargs["forced_aligner_kwargs"] = {
                "dtype": dtype,
                "device_map": self.config.forced_aligner_device_map or self.config.device_map,
            }

        self._model = Qwen3ASRModel.from_pretrained(self.config.model, **kwargs)
        return self._model


def _build_context(free_text: str | None, hotwords: tuple[str, ...]) -> str:
    parts: list[str] = []
    if free_text and free_text.strip():
        parts.append(free_text.strip())
    if hotwords:
        parts.append(
            "以下词语只作为识别候选术语，必须以实际音频为准："
            + "、".join(hotwords)
        )
    return "\n".join(parts)


def _segments_from_words(words: list[TranscriptWord]) -> list[TranscriptSegment]:
    if not words:
        return []

    segments: list[TranscriptSegment] = []
    buffer: list[TranscriptWord] = []

    def emit() -> None:
        if not buffer:
            return
        text = "".join(item.text for item in buffer).strip()
        if text:
            segments.append(
                TranscriptSegment(
                    start=buffer[0].start,
                    end=buffer[-1].end,
                    text=text,
                    words=tuple(buffer),
                )
            )
        buffer.clear()

    for word in words:
        buffer.append(word)
        if any(ch in word.text for ch in "。！？!?"):
            emit()
    emit()
    return segments


def _fallback_range(request: TranscriptionRequest) -> tuple[float, float]:
    if request.source_range is not None:
        return request.source_range.start, request.source_range.end
    duration = _wav_duration(request.audio_path)
    return 0.0, max(duration, 0.001)


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            return handle.getnframes() / rate if rate else 0.0
    except (wave.Error, OSError):
        return 0.001


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))
