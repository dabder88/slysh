from __future__ import annotations

from pathlib import Path

import slysh.runtime_env as runtime_env
from slysh.runtime_env import ENGINE_VENV_DIR, resolve_engine_python


def test_split_engine_venv_only_installed_layout(monkeypatch, tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "Slysh.exe").write_bytes(b"x")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_bytes(b"x")
    monkeypatch.setattr(runtime_env, "install_root", lambda: root)
    monkeypatch.setattr(runtime_env, "use_split_engine_venv", lambda: True)
    assert runtime_env.use_split_engine_venv() is True


def test_resolve_engine_python_prefers_engine_venv(monkeypatch, tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "Slysh.exe").write_bytes(b"x")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_bytes(b"x")
    ui = root / ".venv" / "Scripts"
    eng = root / ENGINE_VENV_DIR / "Scripts"
    ui.mkdir(parents=True)
    eng.mkdir(parents=True)
    (ui / "python.exe").write_bytes(b"ui")
    (eng / "python.exe").write_bytes(b"eng")
    monkeypatch.setattr(runtime_env, "install_root", lambda: root)
    monkeypatch.setattr(runtime_env, "use_split_engine_venv", lambda: True)
    assert Path(resolve_engine_python()) == eng / "python.exe"


def test_dev_tree_uses_sys_executable(monkeypatch):
    monkeypatch.setattr(runtime_env, "use_split_engine_venv", lambda: False)
    import sys

    assert resolve_engine_python() == sys.executable
