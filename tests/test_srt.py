from pathlib import Path

from agent_videonote.transcripts.srt import load_srt


def test_srt_becomes_normalized_transcript(tmp_path: Path) -> None:
    path = tmp_path / "lesson.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\n你好。\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n第二句。\n",
        encoding="utf-8",
    )

    transcript = load_srt(path)

    assert transcript.source_id == "subtitle:srt"
    assert len(transcript.segments) == 2
    assert transcript.segments[0].start == 1.0
    assert transcript.text == "你好。第二句。"
