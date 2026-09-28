from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class DeliveryReport:
    ok: bool
    problems: tuple[str, ...]
    image_references: tuple[str, ...]


def validate_delivery(deliverables_dir: str | Path) -> DeliveryReport:
    root = Path(deliverables_dir)
    transcript = root / "转写全文.md"
    image_dir = root / "画面"
    problems: list[str] = []

    if not transcript.is_file():
        problems.append("缺少 转写全文.md")
        return DeliveryReport(False, tuple(problems), ())

    text = transcript.read_text(encoding="utf-8")
    refs = tuple(match.group(1).strip() for match in _IMAGE_RE.finditer(text))

    if refs and not image_dir.is_dir():
        problems.append("正文存在图片引用，但缺少 画面/ 目录")

    for ref in refs:
        target = (root / ref).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            problems.append(f"图片引用越出交付目录: {ref}")
            continue
        if not target.is_file():
            problems.append(f"图片引用不存在: {ref}")

    return DeliveryReport(not problems, tuple(problems), refs)
