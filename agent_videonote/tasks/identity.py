from __future__ import annotations

import hashlib

from agent_videonote.core.types import SourceIdentity


def task_id_for_source(source: SourceIdentity) -> str:
    if not source.fingerprint:
        # Compatibility fallback for an old in-memory SourceIdentity.
        raw = f"legacy:{source.path.casefold()}:{source.size}:{source.mtime_ns}".encode("utf-8")
    else:
        raw = f"v2:{source.size}:{source.fingerprint}".encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:16]
