from __future__ import annotations

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

        return CleanupResult(
            status="unresolved",
            output_path=None,
            strategy_id="none",
            detail={"attempts": attempts},
        )
