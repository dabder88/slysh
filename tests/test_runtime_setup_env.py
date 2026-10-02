"""Engine install must target .venv-engine in installed layout."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_engine_sync_subprocess_env_sets_uv_project_environment(tmp_path, monkeypatch):
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text('version = "0.0.0"\n', encoding="utf-8")
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))

    from slysh.runtime_env import engine_sync_subprocess_env, engine_venv_dir

    env = engine_sync_subprocess_env()
    assert env["UV_PROJECT_ENVIRONMENT"] == str(engine_venv_dir())
    assert env["VIRTUAL_ENV"] == str(engine_venv_dir())


def test_run_install_passes_engine_env_to_subprocess(tmp_path, monkeypatch):
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text('version = "0.0.0"\n', encoding="utf-8")
    (root / "uv.lock").write_text("", encoding="utf-8")
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "data"))

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        class R:
            returncode = 0

        return R()

    with patch("slysh.runtime_setup.resolve_uv", return_value=str(root / "bin" / "uv.exe")):
        with patch("slysh.runtime_setup.subprocess.run", side_effect=fake_run):
            with patch("slysh.runtime_setup.engine_packages_ok", return_value=True):
                with patch(
                    "slysh.runtime_env.ensure_engine_venv",
                    return_value=root / ".venv-engine" / "Scripts" / "python.exe",
                ):
                    from slysh.runtime_setup import _run_install, reset_install_state_for_tests

                    reset_install_state_for_tests()
                    _run_install()

    assert captured["env"] is not None
    venv_name = Path(captured["env"]["UV_PROJECT_ENVIRONMENT"]).name
    assert venv_name.startswith(".venv-engine")
