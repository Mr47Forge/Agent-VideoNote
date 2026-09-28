from __future__ import annotations

from enum import StrEnum


class AsrCapability(StrEnum):
    SHORT_AUDIO = "transcribe.short_audio"
    LONG_AUDIO = "transcribe.long_audio"
    SEGMENT_TIMESTAMPS = "timestamp.segment"
    WORD_TIMESTAMPS = "timestamp.word"
    HOTWORDS = "context.hotwords"
    FREE_CONTEXT = "context.free_text"
    EXPLICIT_LANGUAGE = "language.explicit"
    BATCH = "batch"
    PERSISTENT_INSTANCE = "runtime.persistent_instance"
    LOCAL = "runtime.local"
    GPU = "runtime.gpu"
