from __future__ import annotations

from typing import Any

from agent_videonote.asr.runtime_config import AsrRuntimeConfig
from agent_videonote.asr.setup.plan import asr_setup_plan


class SetupOperationsMixin:
    def asr_setup_plan(self, search_dirs: list[str] | None = None) -> dict[str, Any]:
        runtime = self.asr_runtime or AsrRuntimeConfig(self.asr_profile, ())
        return asr_setup_plan(self.config, runtime, config_path=self.asr_config_path, search_dirs=search_dirs)
