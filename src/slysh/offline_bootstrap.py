"""Shared offline UI venv repair flags (Slysh.bat / Slysh.exe launcher)."""
from __future__ import annotations

from pathlib import Path

OFFLINE_UV_SYNC_FLAGS = ("--no-editable", "--find-links", "--offline")


def wheelhouse_dir(install_root: Path) -> Path:
    return install_root / "wheelhouse"


def wheelhouse_ready(install_root: Path, *, min_wheels: int = 1) -> bool:
    wh = wheelhouse_dir(install_root)
    if not wh.is_dir():
        return False
    return len(list(wh.glob("*.whl"))) >= min_wheels


def uv_sync_argv(uv_exe: Path, install_root: Path) -> list[str]:
    """Command argv for `uv` (exe not included) to repair UI venv."""
    if wheelhouse_ready(install_root):
        return [
            "sync",
            "--no-editable",
            "--find-links",
            str(wheelhouse_dir(install_root)),
            "--offline",
        ]
    return ["sync"]
