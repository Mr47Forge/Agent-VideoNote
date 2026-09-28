from pathlib import Path

from agent_videonote.asr.context.repository import CourseContext, CourseContextRepository


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
