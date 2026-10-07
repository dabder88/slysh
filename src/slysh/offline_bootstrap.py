"""Shared offline UI venv repair (Slysh.bat / Slysh.exe / runtime_setup)."""
from __future__ import annotations

from pathlib import Path

UI_REQUIREMENTS_FILENAME = "requirements-ui.txt"

# Legacy wheelhouse repair without pinned requirements (pre–F3-04 payloads).
LEGACY_OFFLINE_UV_SYNC_FLAGS = ("--no-editable", "--no-dev", "--find-links", "--offline")

# Preferred offline repair: uv pip sync from wheelhouse + requirements-ui.txt.
OFFLINE_PIP_SYNC_FLAGS = ("--no-index", "--find-links")

# Back-compat alias for tests that only checked legacy sync strings.
OFFLINE_UV_SYNC_FLAGS = LEGACY_OFFLINE_UV_SYNC_FLAGS


def wheelhouse_dir(install_root: Path) -> Path:
    return Path(install_root) / "wheelhouse"


def requirements_ui_path(install_root: Path) -> Path:
    return wheelhouse_dir(install_root) / UI_REQUIREMENTS_FILENAME


def venv_dir(install_root: Path) -> Path:
    return Path(install_root) / ".venv"


def venv_python_path(install_root: Path) -> Path:
    return venv_dir(install_root) / "Scripts" / "python.exe"


def wheelhouse_ready(install_root: Path, *, min_wheels: int = 1) -> bool:
    wh = wheelhouse_dir(install_root)
    if not wh.is_dir():
        return False
    return len(list(wh.glob("*.whl"))) >= min_wheels


def offline_pip_sync_ready(install_root: Path, *, min_wheels: int = 1) -> bool:
    return wheelhouse_ready(install_root, min_wheels=min_wheels) and requirements_ui_path(
        install_root
    ).is_file()


def uv_venv_create_argv(install_root: Path) -> list[str]:
    return ["venv", str(venv_dir(install_root))]


def uv_pip_sync_argv(install_root: Path) -> list[str]:
    root = Path(install_root)
    wh = wheelhouse_dir(root)
    req = requirements_ui_path(root)
    return [
        "pip",
        "sync",
        "--python",
        str(venv_python_path(root)),
        "--no-index",
        "--find-links",
        str(wh),
        str(req),
    ]


def offline_repair_steps(install_root: Path) -> list[list[str]]:
    """Ordered `uv` subcommands (exe name omitted) to repair the light UI venv."""
    root = Path(install_root)
    if offline_pip_sync_ready(root):
        steps: list[list[str]] = []
        if not venv_python_path(root).is_file():
            steps.append(uv_venv_create_argv(root))
        steps.append(uv_pip_sync_argv(root))
        return steps
    if wheelhouse_ready(root):
        return [
            [
                "sync",
                "--no-editable",
                "--no-dev",
                "--find-links",
                str(wheelhouse_dir(root)),
                "--offline",
            ]
        ]
    return [["sync"]]


def uv_sync_argv(uv_exe: Path, install_root: Path) -> list[str]:
    """Single-command repair argv (last step of offline_repair_steps)."""
    steps = offline_repair_steps(install_root)
    return steps[-1]
