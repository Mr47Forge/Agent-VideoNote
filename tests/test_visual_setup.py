from pathlib import Path

from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig
from agent_videonote.visuals.setup import _git_blob_sha1, visual_setup


def _config(tmp_path: Path) -> RuntimeConfig:
    root = tmp_path / "data"
    return RuntimeConfig(
        RuntimePaths(
            root=root,
            tasks=root / "tasks",
            models=root / "models",
            context=root / "context",
            backups=root / "backups",
        )
    )


def test_visual_runtime_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "context" / "visual-runtime.json"
    original = VisualRuntimeConfig(
        vsr_revision="abc",
        vsr_root=str(tmp_path / "third_party" / "vsr"),
        lama_model=str(tmp_path / "models" / "lama.pt"),
        sttn_model=str(tmp_path / "models" / "sttn.pth"),
        propainter_model_dir=str(tmp_path / "models" / "propainter"),
    )

    original.save(path)
    loaded = VisualRuntimeConfig.load(path)

    assert loaded == original


def test_visual_setup_plan_uses_one_python_and_no_nested_venv(tmp_path: Path) -> None:
    result = visual_setup(_config(tmp_path), apply=False)

    assert result["apply"] is False
    assert result["creates_virtualenv"] is False
    assert result["single_python"]
    assert "install_vsr_sparse_source" in result["planned_actions"]
    assert any(item.startswith("download_models:") for item in result["planned_actions"])


def test_git_blob_sha1_matches_git_object_format(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"hello\n")

    assert _git_blob_sha1(path) == "ce013625030ba8dba906f756967f9e9ca394464a"
