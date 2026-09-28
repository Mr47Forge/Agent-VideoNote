from pathlib import Path

from agent_videonote.application.transcript_ops import TranscriptOperationsMixin
from agent_videonote.asr.context.repository import CourseContext, CourseContextRepository
from agent_videonote.asr.request import RecognitionContext


class ContextHarness(TranscriptOperationsMixin):
    pass


def test_course_context_is_persistent_and_deduplicated_on_conversion(tmp_path: Path) -> None:
    repo = CourseContextRepository(tmp_path)
    repo.save(
        CourseContext(
            course_id="m3",
            title_terms=("标题词",),
            glossary_terms=("术语", "标题词"),
            language="zh",
        )
    )

    loaded = repo.load("m3")
    context = repo.to_recognition_context(loaded)

    assert context.language == "zh"
    assert context.hotwords == ("标题词", "术语")

def test_course_context_can_be_extended_for_one_call(tmp_path: Path) -> None:
    repo = CourseContextRepository(tmp_path)
    repo.save(
        CourseContext(
            course_id="m3",
            title_terms=("标题词",),
            glossary_terms=("基础术语",),
            free_text="课程基础上下文",
            language="zh",
        )
    )

    harness = ContextHarness()
    harness.contexts = repo

    context = harness._resolve_context(
        course_id="m3",
        context=RecognitionContext(
            language="zh-CN",
            hotwords=("临时术语", "标题词"),
            free_text="本次片段额外提示",
        ),
    )

    assert context.language == "zh-CN"
    assert context.hotwords == ("标题词", "基础术语", "临时术语")
    assert context.free_text == "课程基础上下文\n本次片段额外提示"

