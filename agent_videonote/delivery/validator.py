from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_DEFAULT_ALLOWED_TOP_LEVEL = {"转写全文.md", "画面"}


@dataclass(frozen=True)
class DeliveryReport:
    ok: bool
    problems: tuple[str, ...]
    image_references: tuple[str, ...]
    orphan_images: tuple[str, ...] = ()
    unexpected_entries: tuple[str, ...] = ()


def validate_delivery(
    deliverables_dir: str | Path,
    *,
    allowed_top_level: set[str] | None = None,
) -> DeliveryReport:
    root = Path(deliverables_dir)
    transcript = root / "转写全文.md"
    image_dir = root / "画面"
    problems: list[str] = []
    allowed = allowed_top_level or _DEFAULT_ALLOWED_TOP_LEVEL

    if not root.is_dir():
        return DeliveryReport(False, ("交付目录不存在",), ())

    unexpected = tuple(
        sorted(item.name for item in root.iterdir() if item.name not in allowed)
    )
    for name in unexpected:
        problems.append(f"交付目录存在未允许条目: {name}")

    if not transcript.is_file():
        problems.append("缺少 转写全文.md")
        return DeliveryReport(False, tuple(problems), (), (), unexpected)

    text = transcript.read_text(encoding="utf-8")
    refs = tuple(match.group(1).strip() for match in _IMAGE_RE.finditer(text))

    referenced_files: set[Path] = set()
    if refs and not image_dir.is_dir():
        problems.append("正文存在图片引用，但缺少 画面/ 目录")

    root_resolved = root.resolve()
    for ref in refs:
        target = (root / ref).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError:
            problems.append(f"图片引用越出交付目录: {ref}")
            continue

        referenced_files.add(target)
        if not target.is_file():
            problems.append(f"图片引用不存在: {ref}")

    orphan_images: list[str] = []
    if image_dir.is_dir():
        for file in image_dir.rglob("*"):
            if not file.is_file():
                continue
            if file.resolve() not in referenced_files:
                relative = file.relative_to(root).as_posix()
                orphan_images.append(relative)
                problems.append(f"画面目录存在未引用图片: {relative}")

    return DeliveryReport(
        ok=not problems,
        problems=tuple(problems),
        image_references=refs,
        orphan_images=tuple(sorted(orphan_images)),
        unexpected_entries=unexpected,
    )
