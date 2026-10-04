from __future__ import annotations

from typing import Any

from agent_videonote.visuals.cleanup.interfaces import CleanupStrategy
from agent_videonote.visuals.cleanup.types import CleanupRequest, CleanupResult


class CleanupRegistry:
    """Runs registered reusable strategies; never creates new code during PROCESS."""

    def __init__(self) -> None:
        self._strategies: list[CleanupStrategy] = []

    def register(self, strategy: CleanupStrategy) -> None:
        if any(item.strategy_id == strategy.strategy_id for item in self._strategies):
            raise ValueError(f"duplicate cleanup strategy: {strategy.strategy_id}")
        self._strategies.append(strategy)

    def resolve(self, request: CleanupRequest) -> CleanupResult:
        attempts: list[dict[str, str]] = []
        for strategy in self._strategies:
            if not strategy.can_handle(request):
                continue
            result = strategy.clean(request)
            if result.resolved:
                return result
            attempts.append({"strategy": strategy.strategy_id, "status": result.status})
            if request.hints.get("provider") == strategy.strategy_id:
                detail = dict(result.detail)
                detail.setdefault("attempts", attempts)
                return CleanupResult(
                    result.status, result.output_path, result.strategy_id, detail
                )

        return CleanupResult(
            status="unresolved", output_path=None, strategy_id="none",
            detail={"attempts": attempts},
        )

    def capabilities(self) -> tuple[dict[str, Any], ...]:
        items: list[dict[str, Any]] = []
        for strategy in self._strategies:
            describe = getattr(strategy, "capabilities", None)
            if callable(describe):
                items.append(dict(describe()))
            else:
                items.append({
                    "strategy_id": strategy.strategy_id,
                    "available": True,
                    "kind": "source_replacement",
                    "requires_mask": False,
                    "requires_gpu": False,
                    "may_use_gpu": False,
                    "external_runtime": False,
                })
        return tuple(items)

    def preflight(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}
        for strategy in self._strategies:
            check = getattr(strategy, "preflight", None)
            result[strategy.strategy_id] = tuple(check()) if callable(check) else ()
        return result
