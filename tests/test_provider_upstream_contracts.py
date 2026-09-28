from pathlib import Path

from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.providers.funasr_auto import (
    FunAsrAutoConfig,
    FunAsrAutoProvider,
)
from agent_videonote.asr.providers.qwen_asr import _qwen_language
from agent_videonote.asr.request import RecognitionContext, TranscriptionRequest


class FakeFunAsrModel:
    def __init__(self):
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return [
            {
                "text": "测试。",
                "sentence_info": [
                    {"text": "测试。", "start": 1000, "end": 2000}
                ],
            }
        ]


def test_funasr_vad_sentence_timestamps_do_not_claim_word_alignment() -> None:
    provider = FunAsrAutoProvider(
        FunAsrAutoConfig(
            provider_id="fun",
            model="placeholder",
            vad_model="fsmn-vad",
            sentence_timestamp=True,
            expect_word_timestamps=False,
        )
    )

    assert AsrCapability.LONG_AUDIO in provider.capabilities
    assert AsrCapability.SEGMENT_TIMESTAMPS in provider.capabilities
    assert AsrCapability.WORD_TIMESTAMPS not in provider.capabilities


def test_funasr_word_timestamps_are_only_claimed_when_explicitly_required() -> None:
    provider = FunAsrAutoProvider(
        FunAsrAutoConfig(
            provider_id="fun",
            model="placeholder",
            vad_model="fsmn-vad",
            sentence_timestamp=False,
            expect_word_timestamps=True,
        )
    )

    assert AsrCapability.SEGMENT_TIMESTAMPS in provider.capabilities
    assert AsrCapability.WORD_TIMESTAMPS in provider.capabilities


def test_funasr_sentence_timestamp_flag_is_sent_and_vad_segments_are_normalized(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"not-used-by-fake")

    provider = FunAsrAutoProvider(
        FunAsrAutoConfig(
            provider_id="fun",
            model="placeholder",
            vad_model="fsmn-vad",
            sentence_timestamp=True,
        )
    )
    fake = FakeFunAsrModel()
    provider._model = fake

    transcript = provider.transcribe(
        TranscriptionRequest(
            audio_path=audio,
            context=RecognitionContext(language="zh", hotwords=("术语",)),
        )
    )

    assert fake.kwargs["sentence_timestamp"] is True
    assert fake.kwargs["language"] == "中文"
    assert fake.kwargs["hotwords"] == ["术语"]
    assert len(transcript.segments) == 1
    assert transcript.segments[0].start == 1.0
    assert transcript.segments[0].end == 2.0
    assert transcript.segments[0].text == "测试。"
    assert transcript.segments[0].words == ()


def test_qwen_language_aliases_match_upstream_canonical_names() -> None:
    assert _qwen_language("zh") == "Chinese"
    assert _qwen_language("zh_CN") == "Chinese"
    assert _qwen_language("en") == "English"
    assert _qwen_language("yue") == "Cantonese"
    assert _qwen_language("Japanese") == "Japanese"
    assert _qwen_language(None) is None
