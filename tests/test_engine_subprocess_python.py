from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_resolve_engine_subprocess_python_prefers_pythonw_on_windows(tmp_path, monkeypatch):
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    scripts = root / ".venv-engine" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_text("", encoding="utf-8")
    (scripts / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))

    from slysh.runtime_env import resolve_engine_python, resolve_engine_subprocess_python

    assert resolve_engine_python().endswith("python.exe")
    if sys.platform == "win32":
        assert resolve_engine_subprocess_python().endswith("pythonw.exe")
    else:
        assert resolve_engine_subprocess_python().endswith("python.exe")
