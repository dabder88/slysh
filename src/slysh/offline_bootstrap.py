"""Shared offline UI venv repair (Slysh.bat / Slysh.exe / runtime_setup)."""
from __future__ import annotations

from pathlib import Path

UI_REQUIREMENTS_FILENAME = "requirements-ui.txt"
PAYLOAD_BUILD_FILENAME = "payload-build.txt"
VENV_PAYLOAD_SYNC_STAMP = ".venv-payload-sync"
PAYLOAD_SYNC_PENDING = ".payload-sync-pending"
INSTALL_UI_LOCALE_SEED = ".install-ui-locale"

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


def payload_build_path(install_root: Path) -> Path:
    return Path(install_root) / PAYLOAD_BUILD_FILENAME


def venv_sync_stamp_path(install_root: Path) -> Path:
    return Path(install_root) / VENV_PAYLOAD_SYNC_STAMP


def _read_stamp_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def read_payload_build_id(install_root: Path) -> str | None:
    return _read_stamp_file(payload_build_path(install_root))


def venv_sync_stamp(install_root: Path) -> str | None:
    return _read_stamp_file(venv_sync_stamp_path(install_root))


def needs_ui_package_resync(install_root: Path) -> bool:
    root = Path(install_root)
    if (root / INSTALL_UI_LOCALE_SEED).is_file():
        return True
    if (root / PAYLOAD_SYNC_PENDING).is_file():
        return True
    build_id = read_payload_build_id(root)
    if not build_id:
        return False
    stamp = venv_sync_stamp(root)
    if not stamp:
        return True
    return stamp.lower() != build_id.lower()


def write_venv_sync_stamp(install_root: Path) -> None:
    root = Path(install_root)
    build_id = read_payload_build_id(root)
    if build_id:
        venv_sync_stamp_path(root).write_text(build_id + "\n", encoding="utf-8")
    pending = root / PAYLOAD_SYNC_PENDING
    if pending.is_file():
        try:
            pending.unlink()
        except OSError:
            pass


def bundled_python_path(install_root: Path) -> Path | None:
    """Portable CPython shipped under runtime/python (installer payload)."""
    rt = Path(install_root) / "runtime" / "python"
    if not rt.is_dir():
        return None
    candidates = sorted(rt.glob("cpython-*/python.exe"))
    if not candidates:
        return None
    return candidates[0]


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
    args: list[str] = ["venv", str(venv_dir(install_root))]
    bundled = bundled_python_path(install_root)
    if bundled is not None:
        args.extend(["--python", str(bundled)])
    return args


def uv_pip_sync_argv(install_root: Path, *, reinstall_slysh: bool = False) -> list[str]:
    root = Path(install_root)
    wh = wheelhouse_dir(root)
    req = requirements_ui_path(root)
    args = [
        "pip",
        "sync",
        "--python",
        str(venv_python_path(root)),
        "--no-index",
        "--find-links",
        str(wh),
        str(req),
    ]
    if reinstall_slysh:
        args.extend(["--reinstall-package", "slysh"])
    return args


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
