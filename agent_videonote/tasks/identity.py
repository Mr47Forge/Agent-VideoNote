from __future__ import annotations

import hashlib
import json

from agent_videonote.core.types import SourceIdentity


def task_id_for_source(source: SourceIdentity) -> str:
    payload = {
        "path": source.path.casefold(),
        "size": source.size,
        "mtime_ns": source.mtime_ns,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
