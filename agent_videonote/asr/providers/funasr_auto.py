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
class FunAsrAutoConfig:
    provider_id: str
    model: str
    hub: str = "ms"
    device: str = "cuda:0"
    vad_model: str | None = "fsmn-vad"
    vad_max_single_segment_time: int = 30000
    trust_remote_code: bool = True
    sentence_timestamp: bool = False
    expect_word_timestamps: bool = False
    itn: bool = True
    batch_size: int = 1
    extra_init: dict[str, Any] = field(default_factory=dict)
    extra_generate: dict[str, Any] = field(default_factory=dict)


class FunAsrAutoProvider:
    """Generic FunASR AutoModel provider. No model ID is hard-coded."""

    def __init__(self, config: FunAsrAutoConfig):
        if not config.provider_id.strip():
            raise ConfigurationError("provider_id cannot be empty")
        if not config.model.strip():
            raise ConfigurationError("FunASR model cannot be empty")
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
            AsrCapability.EXPLICIT_LANGUAGE,
            AsrCapability.PERSISTENT_INSTANCE,
            AsrCapability.LOCAL,
        }
        if self.config.vad_model:
            caps.add(AsrCapability.LONG_AUDIO)
        if self.config.sentence_timestamp or self.config.expect_word_timestamps:
            caps.add(AsrCapability.SEGMENT_TIMESTAMPS)
        if self.config.expect_word_timestamps:
            caps.add(AsrCapability.WORD_TIMESTAMPS)
        if self.config.device.lower().startswith("cuda"):
            caps.add(AsrCapability.GPU)
        return frozenset(caps)

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        model = self._ensure_model()
        kwargs: dict[str, Any] = {
            "input": [str(request.audio_path)],
            "cache": {},
            "batch_size": self.config.batch_size,
            "itn": self.config.itn,
            **self.config.extra_generate,
        }
        if request.context.hotwords:
            kwargs["hotwords"] = list(request.context.hotwords)
        if request.context.language:
            kwargs["language"] = _funasr_language(request.context.language)
        if self.config.sentence_timestamp:
            kwargs["sentence_timestamp"] = True

        raw_results = model.generate(**kwargs)
        if not isinstance(raw_results, list) or not raw_results:
            raise CapabilityError(f"{self.provider_id} returned no transcription result")

        offset = request.source_range.start if request.source_range else 0.0
        words: list[TranscriptWord] = []
        segments: list[TranscriptSegment] = []
        text_parts: list[str] = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if text:
                text_parts.append(text)

            item_words = _extract_words(item, offset=offset)
            if item_words:
                words.extend(item_words)
                segments.extend(_segments_from_words(item_words))
                continue

            sentence_info = item.get("sentence_info")
            if isinstance(sentence_info, list):
                for sentence in sentence_info:
                    if not isinstance(sentence, dict):
                        continue
                    sentence_text = str(sentence.get("text") or "").strip()
                    start = _milliseconds_to_seconds(sentence.get("start"), offset)
                    end = _milliseconds_to_seconds(sentence.get("end"), offset)
                    if sentence_text and start is not None and end is not None and end > start:
                        segments.append(
                            TranscriptSegment(start=start, end=end, text=sentence_text)
                        )

        if self.config.sentence_timestamp and not segments:
            raise CapabilityError(
                f"{self.provider_id} was configured to require segment timestamps, "
                "but this pipeline returned none"
            )
        if self.config.expect_word_timestamps and not words:
            raise CapabilityError(
                f"{self.provider_id} was configured to require word timestamps, "
                "but this model/checkpoint returned none"
            )

        full_text = "".join(text_parts)
        if not segments and full_text:
            start, end = _fallback_range(request)
            segments.append(TranscriptSegment(start=start, end=end, text=full_text))

        return Transcript(
            text=full_text,
            segments=tuple(_dedupe_segments(segments)),
            source_id=f"asr:{self.provider_id}",
            language=request.context.language,
            metadata={
                "framework": "funasr.AutoModel",
                "model": self.config.model,
                "hub": self.config.hub,
            },
        )

    def close(self) -> None:
        self._model = None
        try:
            import torch
            if self.config.device.lower().startswith("cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise ConfigurationError(
                "FunASR provider requires the upstream 'funasr' package"
            ) from exc

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "hub": self.config.hub,
            "device": self.config.device,
            "trust_remote_code": self.config.trust_remote_code,
            "disable_update": True,
            **self.config.extra_init,
        }
        if self.config.vad_model:
            kwargs["vad_model"] = self.config.vad_model
            kwargs["vad_kwargs"] = {
                "max_single_segment_time": self.config.vad_max_single_segment_time
            }

        self._model = AutoModel(**kwargs)
        return self._model


def _extract_words(item: dict[str, Any], *, offset: float) -> list[TranscriptWord]:
    timestamps = item.get("timestamps")
    if isinstance(timestamps, list) and timestamps and isinstance(timestamps[0], dict):
        result: list[TranscriptWord] = []
        for ts in timestamps:
            token = str(ts.get("token") or "")
            start = ts.get("start_time")
            end = ts.get("end_time")
            if token and _is_number(start) and _is_number(end) and float(end) > float(start):
                result.append(
                    TranscriptWord(
                        start=float(start) + offset,
                        end=float(end) + offset,
                        text=token,
                    )
                )
        return result

    timestamp_pairs = item.get("timestamp")
    word_list = item.get("words")
    if (
        isinstance(timestamp_pairs, list)
        and isinstance(word_list, list)
        and len(timestamp_pairs) == len(word_list)
    ):
        result = []
        for word, pair in zip(word_list, timestamp_pairs):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            if not _is_number(pair[0]) or not _is_number(pair[1]):
                continue
            result.append(
                TranscriptWord(
                    start=float(pair[0]) / 1000.0 + offset,
                    end=float(pair[1]) / 1000.0 + offset,
                    text=str(word),
                )
            )
        return result

    return []


def _segments_from_words(words: list[TranscriptWord]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    buffer: list[TranscriptWord] = []

    def emit() -> None:
        if not buffer:
            return
        segments.append(
            TranscriptSegment(
                start=buffer[0].start,
                end=buffer[-1].end,
                text="".join(item.text for item in buffer).strip(),
                words=tuple(buffer),
            )
        )
        buffer.clear()

    for word in words:
        buffer.append(word)
        if any(ch in word.text for ch in "。！？!?"):
            emit()
    emit()
    return [segment for segment in segments if segment.text]


def _dedupe_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    result: list[TranscriptSegment] = []
    for segment in sorted(segments, key=lambda item: (item.start, item.end)):
        if result and segment.start == result[-1].start and segment.end == result[-1].end and segment.text == result[-1].text:
            continue
        result.append(segment)
    return result


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


def _milliseconds_to_seconds(value: Any, offset: float) -> float | None:
    if not _is_number(value):
        return None
    return float(value) / 1000.0 + offset


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))


def _funasr_language(value: str) -> str:
    mapping = {
        "zh": "中文",
        "chinese": "中文",
        "en": "英文",
        "english": "英文",
        "ja": "日文",
        "japanese": "日文",
    }
    return mapping.get(value.strip().lower(), value)
