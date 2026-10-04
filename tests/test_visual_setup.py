from pathlib import Path
import io

from agent_videonote.core.config import RuntimeConfig, RuntimePaths
from agent_videonote.visuals.runtime_config import VisualRuntimeConfig
from agent_videonote.visuals.setup import (
    VSR_REVISION,
    _VSR_REQUIRED_FILES,
    _download_verified,
    _git_blob_sha1,
    _install_models,
    _install_vsr_source,
    _model_file_ready,
    _package_installer,
    _paths,
    _source_ready,
    _status,
    visual_setup,
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


def test_model_file_ready_rejects_truncation_and_wrong_blob(tmp_path: Path) -> None:
    path = tmp_path / "model.bin"
    path.write_bytes(b"hello\n")

    assert _model_file_ready(path, expected_size=6) is True
    assert _model_file_ready(path, expected_size=7) is False
    assert _model_file_ready(
        path,
        expected_size=6,
        blob_sha="ce013625030ba8dba906f756967f9e9ca394464a",
    ) is True
    assert _model_file_ready(
        path,
        expected_size=6,
        blob_sha="0" * 40,
    ) is False


def test_visual_setup_status_does_not_mark_truncated_model_ready(tmp_path: Path) -> None:
    config = _config(tmp_path)
    paths = _paths(config)
    paths.model_root.mkdir(parents=True, exist_ok=True)
    (paths.model_root / "big-lama.pt").write_bytes(b"truncated")

    result = _status(paths, VisualRuntimeConfig.disabled())

    assert result["models"]["lama"]["ready"] is False
    assert result["models"]["lama"]["actual_size"] == len(b"truncated")
    assert result["models"]["lama"]["expected_size"] > result["models"]["lama"]["actual_size"]


def test_install_models_repairs_existing_truncated_final_files(
        tmp_path: Path, monkeypatch) -> None:
    from agent_videonote.visuals import setup

    root = tmp_path / "models"
    root.mkdir()
    (root / "big-lama.pt").write_bytes(b"bad")
    propainter = root / "propainter" / "ProPainter.pth"
    propainter.parent.mkdir(parents=True)
    propainter.write_bytes(b"bad")

    joined_calls = []
    direct_calls = []

    monkeypatch.setattr(
        setup,
        "_download_joined",
        lambda parts, target: joined_calls.append(Path(target)),
    )
    monkeypatch.setattr(
        setup,
        "_download_blob",
        lambda remote, blob_sha, size, target: direct_calls.append(Path(target)),
    )

    actions = []
    _install_models(root, actions)

    assert root / "big-lama.pt" in joined_calls
    assert propainter in joined_calls
    assert len(direct_calls) == 3
    assert "downloaded_big_lama" in actions
    assert "downloaded_propainter" in actions


def test_vsr_correct_revision_but_missing_sparse_files_is_repaired(
        tmp_path: Path, monkeypatch) -> None:
    from agent_videonote.visuals import setup

    root = tmp_path / "vsr"
    (root / ".git").mkdir(parents=True)
    calls = []

    monkeypatch.setattr(setup.shutil, "which", lambda name: "git")
    monkeypatch.setattr(setup, "_capture", lambda command: VSR_REVISION + "\n")

    def fake_run(command):
        calls.append(command)
        if "checkout" in command:
            for relative in _VSR_REQUIRED_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# restored\n", encoding="utf-8")

    monkeypatch.setattr(setup, "_run", fake_run)

    assert _source_ready(root) is False
    actions = []
    _install_vsr_source(root, actions)

    assert _source_ready(root) is True
    assert any("sparse-checkout" in command for command in calls)
    assert any("checkout" in command for command in calls)
    assert actions == [f"installed_vsr_source:{VSR_REVISION}"]


def test_vsr_complete_correct_revision_skips_git_work(
        tmp_path: Path, monkeypatch) -> None:
    from agent_videonote.visuals import setup

    root = tmp_path / "vsr"
    (root / ".git").mkdir(parents=True)
    for relative in _VSR_REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# ready\n", encoding="utf-8")

    monkeypatch.setattr(setup.shutil, "which", lambda name: "git")
    monkeypatch.setattr(setup, "_capture", lambda command: VSR_REVISION + "\n")
    monkeypatch.setattr(
        setup,
        "_run",
        lambda command: (_ for _ in ()).throw(
            AssertionError("complete fixed revision must not run git mutation")
        ),
    )

    actions = []
    _install_vsr_source(root, actions)

    assert actions == []
