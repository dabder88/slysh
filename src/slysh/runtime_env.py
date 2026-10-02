"""Installed layout: light UI venv + heavy engine venv. Dev tree keeps one shared .venv."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from slysh.paths import install_root, project_root

UI_VENV_DIR = ".venv"
ENGINE_VENV_DIR = ".venv-engine"
ENGINE_VENV_PREFIX = ".venv-engine-"
RUNTIME_MANIFEST = "runtime-env.json"


def use_split_engine_venv() -> bool:
    from slysh.release_version import installed_app_layout

    return installed_app_layout()


def ui_venv_dir() -> Path:
    return install_root() / UI_VENV_DIR


def engine_venv_dir() -> Path:
    return install_root() / ENGINE_VENV_DIR


def engine_venv_dir_for_fingerprint(fingerprint: str) -> Path:
    safe = "".join(c for c in fingerprint.lower() if c in "0123456789abcdef")[:16]
    if not safe:
        safe = "default"
    return install_root() / f"{ENGINE_VENV_PREFIX}{safe}"


def resolve_engine_venv_target() -> Path:
    from slysh.updates import uv_lock_fingerprint

    fp = uv_lock_fingerprint()
    if fp:
        return engine_venv_dir_for_fingerprint(fp)
    return engine_venv_dir()


def active_engine_venv_dir() -> Path:
    manifest = read_runtime_manifest()
    name = str(manifest.get("active_engine_venv") or "").strip()
    if name:
        candidate = install_root() / name
        if _venv_python(candidate).is_file():
            return candidate
    legacy = engine_venv_dir()
    if _venv_python(legacy).is_file():
        return legacy
    return resolve_engine_venv_target()


def _venv_python(venv_root: Path) -> Path:
    return venv_root / "Scripts" / "python.exe"


def _venv_pythonw(venv_root: Path) -> Path:
    return venv_root / "Scripts" / "pythonw.exe"


def ui_python_executable() -> Path:
    return _venv_python(ui_venv_dir())


def engine_python_executable() -> Path | None:
    path = _venv_python(active_engine_venv_dir())
    return path if path.is_file() else None


def _resolve_engine_python_exe() -> str:
    if use_split_engine_venv():
        eng = engine_python_executable()
        if eng is not None:
            return str(eng)
        ui = ui_python_executable()
        if ui.is_file():
            return str(ui)
    return sys.executable


def _prefer_pythonw_for_subprocess(exe: str) -> str:
    if sys.platform != "win32":
        return exe
    path = Path(exe)
    if path.name.lower() != "python.exe":
        return exe
    pyw = path.with_name("pythonw.exe")
    return str(pyw) if pyw.is_file() else exe


def read_ui_venv_home() -> Path | None:
    """``pyvenv.cfg`` ``home`` for the light UI ``.venv`` (uv managed runtime)."""
    cfg = ui_venv_dir() / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("home = "):
            raw = line.split("=", 1)[1].strip()
            if raw:
                return Path(raw)
    return None


def uv_ui_shim_should_yield() -> bool:
    """True when this process is ``.venv\\Scripts\\pythonw`` and uv will run ``home\\pythonw``."""
    if not use_split_engine_venv():
        return False
    try:
        exe = Path(sys.executable).resolve()
    except OSError:
        return False
    ui = ui_venv_dir()
    shim_pyw = _venv_pythonw(ui).resolve()
    shim_py = _venv_python(ui).resolve()
    if exe not in (shim_pyw, shim_py):
        return False
    home = read_ui_venv_home()
    if home is None or not home.is_dir():
        return False
    try:
        home = home.resolve()
        root = install_root().resolve()
    except OSError:
        return False
    if not str(home).startswith(str(root)):
        return False
    return (home / "pythonw.exe").is_file()


def resolve_engine_python() -> str:
    """Engine venv ``python.exe`` (for ``uv --python``, paths)."""
    return _resolve_engine_python_exe()


def resolve_engine_subprocess_python() -> str:
    """Hidden child processes: probe, engine_server, model download."""
    return _prefer_pythonw_for_subprocess(_resolve_engine_python_exe())


def engine_subprocess_python_for_venv(venv_root: Path) -> str:
    """Probe/import python for a specific engine venv directory (e.g. fresh install slot)."""
    return _prefer_pythonw_for_subprocess(str(_venv_python(venv_root)))


def revert_active_engine_venv() -> bool:
    """Switch back to ``previous_engine_venv`` if its python exists (failed upgrade)."""
    if not use_split_engine_venv():
        return False
    manifest = read_runtime_manifest()
    prev = str(manifest.get("previous_engine_venv") or "").strip()
    if not prev:
        return False
    prev_dir = install_root() / prev
    if not _venv_python(prev_dir).is_file():
        return False
    write_runtime_manifest(active_slot=prev)
    return True


def engine_sync_subprocess_env() -> dict[str, str]:
    """Environment so ``uv sync`` targets the engine venv, not the light UI ``.venv``."""
    env = os.environ.copy()
    if use_split_engine_venv():
        venv = resolve_engine_venv_target()
        env["UV_PROJECT_ENVIRONMENT"] = str(venv)
        env["VIRTUAL_ENV"] = str(venv)
    return env


def ensure_engine_venv(uv: str, target: Path | None = None) -> Path:
    """Create engine venv directory if missing (installed layout only)."""
    root = project_root()
    venv_root = target or resolve_engine_venv_target()
    py = _venv_python(venv_root)
    if py.is_file():
        return py
    venv_root.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    from slysh.subprocess_win import subprocess_no_console_kwargs

    proc = subprocess.run(
        [uv, "venv", str(venv_root)],
        cwd=str(root),
        check=False,
        **subprocess_no_console_kwargs(),
    )
    if proc.returncode != 0 or not py.is_file():
        raise RuntimeError(f"Не удалось создать окружение engine: {venv_root}")
    return py


def write_runtime_manifest(*, active_slot: str | None = None) -> None:
    if not use_split_engine_venv():
        return
    from slysh.updates import uv_lock_fingerprint

    previous = read_runtime_manifest()
    slot = active_slot or str(previous.get("active_engine_venv") or "").strip()
    if not slot:
        target = resolve_engine_venv_target()
        slot = target.name
    prev_slot = previous.get("active_engine_venv")
    payload = {
        "ui_venv": UI_VENV_DIR,
        "engine_venv": ENGINE_VENV_DIR,
        "active_engine_venv": slot,
        "previous_engine_venv": (
            prev_slot
            if active_slot and prev_slot and prev_slot != active_slot
            else previous.get("previous_engine_venv")
        ),
        "lock_fingerprint": uv_lock_fingerprint(),
    }
    path = install_root() / RUNTIME_MANIFEST
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
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
