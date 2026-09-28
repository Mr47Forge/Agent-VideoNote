from __future__ import annotations

from pathlib import Path

from agent_videonote.lifecycle.types import CleanupCandidate, CleanupPlan


def plan_safe_cleanup(task_id: str, task_dir: str | Path) -> CleanupPlan:
    """Plan only clearly reproducible/intermediate files. Does not delete anything."""
    root = Path(task_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)

    candidates: list[CleanupCandidate] = []

    temp_dir = root / "temp"
    if temp_dir.is_dir():
        for path in _regular_files(temp_dir):
            candidates.append(
                CleanupCandidate(
                    path=str(path),
                    bytes=path.stat().st_size,
                    reason="task-temp",
                )
            )

    review_audio = root / "reviews" / "audio"
    review_results = root / "reviews" / "results"
    if review_audio.is_dir() and review_results.is_dir():
        for path in _regular_files(review_audio):
            result = review_results / f"{path.stem}.json"
            if result.is_file():
                candidates.append(
                    CleanupCandidate(
                        path=str(path),
                        bytes=path.stat().st_size,
                        reason="review-audio-has-persisted-result",
                    )
                )

    # Atomic-write leftovers are internal implementation debris. The active
    # lock file is intentionally not included.
    for path in _regular_files(root):
        if path.name.endswith(".tmp") and path.name != ".state.lock":
            candidates.append(
                CleanupCandidate(
                    path=str(path),
                    bytes=path.stat().st_size,
                    reason="orphan-atomic-temp",
                )
            )

    unique = {
        item.path: item
        for item in candidates
    }
    return CleanupPlan(
        task_id=task_id,
        candidates=tuple(unique[path] for path in sorted(unique)),
    )


def _regular_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path
