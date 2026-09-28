from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.types import Transcript, TranscriptionRequest


@runtime_checkable
class AsrProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[AsrCapability]: ...

    def transcribe(self, request: TranscriptionRequest) -> Transcript: ...

    def close(self) -> None: ...
