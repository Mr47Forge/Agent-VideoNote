from pathlib import Path

from agent_videonote.delivery.validator import validate_delivery


def test_delivery_detects_missing_image(tmp_path: Path) -> None:
    (tmp_path / "转写全文.md").write_text(
        "正文\n\n![图](画面/001.jpg)\n",
        encoding="utf-8",
    )
    (tmp_path / "画面").mkdir()

    report = validate_delivery(tmp_path)

    assert not report.ok
    assert any("图片引用不存在" in item for item in report.problems)


def test_delivery_accepts_existing_image(tmp_path: Path) -> None:
    (tmp_path / "画面").mkdir()
    (tmp_path / "画面" / "001.jpg").write_bytes(b"jpg")
    (tmp_path / "转写全文.md").write_text(
        "正文\n\n![图](画面/001.jpg)\n",
        encoding="utf-8",
    )

    report = validate_delivery(tmp_path)

    assert report.ok
