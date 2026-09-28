from __future__ import annotations

from threading import BoundedSemaphore

from agent_videonote.asr.providers.base import AsrProvider
from agent_videonote.asr.request import TranscriptionRequest
from agent_videonote.transcripts.types import Transcript


class ConcurrencyGuardProvider:
    """Serialize or bound concurrent calls without coupling model code to MCP."""

    def __init__(self, provider: AsrProvider, *, max_concurrency: int = 1):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._provider = provider
        self._semaphore = BoundedSemaphore(max_concurrency)
        self.max_concurrency = max_concurrency

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    @property
    def capabilities(self):
        return self._provider.capabilities

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        with self._semaphore:
            return self._provider.transcribe(request)

    def close(self) -> None:
        self._provider.close()
