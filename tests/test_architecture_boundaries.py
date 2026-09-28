import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_application_service_remains_a_thin_facade() -> None:
    path = ROOT / "agent_videonote" / "application" / "service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ApplicationService"
    ]
    assert len(classes) == 1

    methods = {
        node.name
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {"__init__"}


def test_mcp_server_does_not_import_core_implementations_directly() -> None:
    path = ROOT / "agent_videonote" / "adapters" / "mcp" / "server.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden_prefixes = (
        "agent_videonote.media.",
        "agent_videonote.asr.providers.",
        "agent_videonote.visuals.",
        "agent_videonote.storage.",
        "agent_videonote.tasks.",
    )

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    offenders = [
        name
        for name in imports
        if any(name.startswith(prefix) for prefix in forbidden_prefixes)
    ]
    assert offenders == []

def test_task_state_writers_use_atomic_mutate() -> None:
    task_service = (
        ROOT / "agent_videonote" / "tasks" / "service.py"
    ).read_text(encoding="utf-8")
    workflow_engine = (
        ROOT / "agent_videonote" / "workflow" / "engine.py"
    ).read_text(encoding="utf-8")

    assert "._store.save(" not in task_service
    assert ".store.save(" not in workflow_engine
    assert "._store.mutate(" in task_service
    assert ".store.mutate(" in workflow_engine

