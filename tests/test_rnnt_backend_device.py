import ast
import builtins
from pathlib import Path

from slysh.rnnt_backend import resolve_device

BACKEND_SRC = (
    Path(__file__).resolve().parents[1] / "src" / "slysh" / "rnnt_backend.py"
)


def test_force_cpu(monkeypatch):
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "true")
    assert resolve_device() == "cpu"


def test_force_cpu_skips_torch_import(monkeypatch):
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "1")
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("torch must not be imported when GIGAAM_FORCE_CPU is set")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert resolve_device() == "cpu"


def test_force_cpu_yes(monkeypatch):
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "yes")
    assert resolve_device() == "cpu"


def test_device_env_cpu_skips_torch(monkeypatch):
    monkeypatch.delenv("GIGAAM_FORCE_CPU", raising=False)
    monkeypatch.setenv("GIGAAM_DEVICE", "cpu")
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("torch must not be imported when GIGAAM_DEVICE=cpu")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert resolve_device() == "cpu"


def _top_level_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module.split(".")[0])
    return names


def _function_imports(fn: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_rnnt_backend_lazy_imports_via_ast():
    tree = ast.parse(BACKEND_SRC.read_text(encoding="utf-8"))
    top = _top_level_imports(tree)
    assert "torch" not in top
    assert "gigaam" not in top

    resolve = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_device"
    )
    assert "torch" in _function_imports(resolve)

    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GigaAMBackend")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    assert "gigaam" in _function_imports(init)
    assert "gigaam" not in _function_imports(resolve)
    assert "torch" not in _function_imports(init)

    # torch import must sit on the non-force path (after the FORCE_CPU early return).
    force_return_lineno = None
    for node in resolve.body:
        if isinstance(node, ast.If):
            if_src = ast.get_source_segment(BACKEND_SRC.read_text(encoding="utf-8"), node.test) or ""
            if "GIGAAM_FORCE_CPU" in if_src:
                for stmt in node.body:
                    if isinstance(stmt, ast.Return):
                        force_return_lineno = stmt.lineno
                        break
        if force_return_lineno is not None:
            break
    assert force_return_lineno is not None

    torch_import_lineno = None
    for node in ast.walk(resolve):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "torch" for a in node.names):
            torch_import_lineno = node.lineno
            break
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("torch"):
            torch_import_lineno = node.lineno
            break
    assert torch_import_lineno is not None
    assert torch_import_lineno > force_return_lineno
