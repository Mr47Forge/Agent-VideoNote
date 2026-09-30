from pathlib import Path
import io

from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig
from agent_videonote.visuals.setup import (
    _download_verified, _git_blob_sha1, _package_installer, visual_setup,
)


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


def test_uv_installs_into_current_python_when_pip_is_absent(monkeypatch) -> None:
    import sys
    from agent_videonote.visuals import setup

    monkeypatch.setattr(setup.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "uv.exe")
    assert _package_installer() == ["uv.exe", "pip", "install", "--python", sys.executable]


def test_model_download_resumes_truncated_response_and_checks_blob(tmp_path, monkeypatch) -> None:
    from agent_videonote.visuals import setup

    calls = []

    class Response(io.BytesIO):
        def __init__(self, data: bytes, status: int):
            super().__init__(data)
            self.status = status

    def fake_urlopen(request, timeout):
        offset = request.get_header("Range")
        calls.append(offset)
        return Response(b"he", 200) if offset is None else Response(b"llo\n", 206)

    monkeypatch.setattr(setup.urllib.request, "urlopen", fake_urlopen)
    target = tmp_path / "model.part"
    _download_verified("test/model.part", "ce013625030ba8dba906f756967f9e9ca394464a", 6, target)
    assert target.read_bytes() == b"hello\n"
    assert calls == [None, "bytes=2-"]
