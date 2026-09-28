import json
import sys
from pathlib import Path

from agent_videonote.application.factory import build_runtime_from_environment
from agent_videonote.core.config import RuntimeConfig, RuntimePaths


def _config(tmp_path: Path) -> RuntimeConfig:
    root = tmp_path / "data"
    paths = RuntimePaths(
        root=root,
        tasks=root / "tasks",
        models=root / "models",
        context=root / "context",
        backups=root / "backups",
    )
    paths.context.mkdir(parents=True, exist_ok=True)
    return RuntimeConfig(
        paths=paths,
        ffmpeg_bin=sys.executable,
        ffprobe_bin=sys.executable,
    )


def test_invalid_asr_json_degrades_runtime_instead_of_blocking_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    source = config.paths.context / "broken-asr.json"
    source.write_text("{ definitely-not-json", encoding="utf-8")
    monkeypatch.setenv("AGENT_VIDEONOTE_ASR_CONFIG", str(source))

    container = build_runtime_from_environment(config=config)
    result = container.application.health()

    assert result["status"] == "degraded"
    assert result["models_loaded"] is False
    assert result["asr"]["roles"]["primary"]["enabled"] is False
    assert any("ASR runtime config disabled" in item for item in result["warnings"])


def test_unknown_provider_driver_is_reported_but_other_runtime_still_builds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    source = config.paths.context / "asr.json"
    source.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "broken",
                        "driver": "does-not-exist",
                        "options": {},
                    }
                ],
                "roles": {
                    "primary": "broken",
                    "review": None,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_VIDEONOTE_ASR_CONFIG", str(source))

    container = build_runtime_from_environment(config=config)
    result = container.application.health()

    assert result["status"] == "degraded"
    assert result["asr"]["roles"]["primary"]["registered"] is False
    assert any("was not registered" in item for item in result["warnings"])
    assert any("references unregistered provider" in item for item in result["warnings"])
