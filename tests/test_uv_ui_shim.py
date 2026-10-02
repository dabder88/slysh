from __future__ import annotations

import sys
from pathlib import Path


def test_uv_ui_shim_should_yield_for_venv_scripts_pythonw(tmp_path, monkeypatch):
    root = tmp_path / "app"
    scripts = root / ".venv" / "Scripts"
    home = root / "runtime" / "python" / "cpython-3.12"
    scripts.mkdir(parents=True)
    home.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "bin" / "uv.exe").parent.mkdir(parents=True, exist_ok=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    (scripts / "pythonw.exe").write_text("", encoding="utf-8")
    (home / "pythonw.exe").write_text("", encoding="utf-8")
    (root / ".venv" / "pyvenv.cfg").write_text(
        f"home = {home}\nimplementation = CPython\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    monkeypatch.setattr(sys, "executable", str(scripts / "pythonw.exe"))

    from slysh.release_version import installed_app_layout
    from slysh.runtime_env import uv_ui_shim_should_yield

    installed_app_layout.cache_clear()
    assert uv_ui_shim_should_yield() is True


def test_uv_ui_shim_false_for_home_pythonw(tmp_path, monkeypatch):
    root = tmp_path / "app"
    scripts = root / ".venv" / "Scripts"
    home = root / "runtime" / "python" / "cpython-3.12"
    scripts.mkdir(parents=True)
    home.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    (scripts / "pythonw.exe").write_text("", encoding="utf-8")
    (home / "pythonw.exe").write_text("", encoding="utf-8")
    (root / ".venv" / "pyvenv.cfg").write_text(
        f"home = {home}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    monkeypatch.setattr(sys, "executable", str(home / "pythonw.exe"))

    from slysh.release_version import installed_app_layout
    from slysh.runtime_env import uv_ui_shim_should_yield

    installed_app_layout.cache_clear()
    assert uv_ui_shim_should_yield() is False
