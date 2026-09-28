from __future__ import annotations

from typing import Any


class CatalogOperationsMixin:
    def list_asr_models(
        self,
        *,
        role: str | None = None,
        priority: str = "balanced",
        integrated_only: bool = False,
        limit: int = 5,
        detail: str = "compact",
    ) -> dict[str, Any]:
        return self.model_catalog.list_models(
            role=role,
            priority=priority,
            integrated_only=integrated_only,
            limit=limit,
            detail=detail,
        )
