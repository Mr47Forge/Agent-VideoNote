from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import time

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.providers.guard import ConcurrencyGuardProvider
from agent_videonote.asr.request import RecognitionContext, TranscriptionRequest
from agent_videonote.transcripts.types import Transcript, TranscriptSegment


class SlowProvider:
    provider_id = "slow"
    capabilities = frozenset({AsrCapability.SHORT_AUDIO})

    def __init__(self):
        self._lock = Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    def transcribe(self, request):
        with self._lock:
            self.active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.03)
            return Transcript(
                text="ok",
                segments=(TranscriptSegment(start=0.0, end=1.0, text="ok"),),
                source_id="slow",
            )
        finally:
            with self._lock:
                self.active -= 1

    def close(self) -> None:
        pass


def _request(tmp_path: Path) -> TranscriptionRequest:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    return TranscriptionRequest(audio_path=audio, context=RecognitionContext())


def test_concurrency_guard_serializes_by_default(tmp_path: Path) -> None:
    inner = SlowProvider()
    provider = ConcurrencyGuardProvider(inner)
    request = _request(tmp_path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: provider.transcribe(request), range(4)))

    assert len(results) == 4
    assert inner.calls == 4
    assert inner.max_active == 1


def test_concurrency_guard_allows_explicit_parallelism(tmp_path: Path) -> None:
    inner = SlowProvider()
    provider = ConcurrencyGuardProvider(inner, max_concurrency=2)
    request = _request(tmp_path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: provider.transcribe(request), range(4)))

    assert inner.max_active <= 2
    assert inner.max_active >= 2
