"""Installed layout: light UI venv + heavy engine venv. Dev tree keeps one shared .venv."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from slysh.paths import install_root, project_root

UI_VENV_DIR = ".venv"
ENGINE_VENV_DIR = ".venv-engine"
RUNTIME_MANIFEST = "runtime-env.json"


def use_split_engine_venv() -> bool:
    from slysh.release_version import installed_app_layout

    return installed_app_layout()


def ui_venv_dir() -> Path:
    return install_root() / UI_VENV_DIR


def engine_venv_dir() -> Path:
    return install_root() / ENGINE_VENV_DIR


def _venv_python(venv_root: Path) -> Path:
    return venv_root / "Scripts" / "python.exe"


def ui_python_executable() -> Path:
    return _venv_python(ui_venv_dir())


def engine_python_executable() -> Path | None:
    path = _venv_python(engine_venv_dir())
    return path if path.is_file() else None


def resolve_engine_python() -> str:
    if use_split_engine_venv():
        eng = engine_python_executable()
        if eng is not None:
            return str(eng)
        ui = ui_python_executable()
        if ui.is_file():
            return str(ui)
    return sys.executable


def ensure_engine_venv(uv: str) -> Path:
    """Create engine venv directory if missing (installed layout only)."""
    root = project_root()
    target = engine_venv_dir()
    py = _venv_python(target)
    if py.is_file():
        return py
    target.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    from slysh.subprocess_win import subprocess_no_console_kwargs

    proc = subprocess.run(
        [uv, "venv", str(target)],
        cwd=str(root),
        check=False,
        **subprocess_no_console_kwargs(),
    )
    if proc.returncode != 0 or not py.is_file():
        raise RuntimeError(f"Не удалось создать окружение engine: {target}")
    return py


def write_runtime_manifest() -> None:
    if not use_split_engine_venv():
        return
    from slysh.updates import uv_lock_fingerprint

    payload = {
        "ui_venv": UI_VENV_DIR,
        "engine_venv": ENGINE_VENV_DIR,
        "lock_fingerprint": uv_lock_fingerprint(),
    }
    path = install_root() / RUNTIME_MANIFEST
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_runtime_manifest() -> dict:
    path = install_root() / RUNTIME_MANIFEST
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
