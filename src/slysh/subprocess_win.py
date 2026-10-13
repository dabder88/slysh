"""Windows subprocess helpers (hide console for GUI app)."""
from __future__ import annotations

import subprocess
import sys


def install_subprocess_hide_console_patch() -> None:
    """Merge CREATE_NO_WINDOW into every Popen in this process (engine / gigaam)."""
    if sys.platform != "win32":
        return
    if getattr(subprocess, "_slysh_no_console_patched", False):
        return
    _orig_popen = subprocess.Popen
    _extra = subprocess_no_console_kwargs()

    def _popen(*args, **kwargs):
        if "startupinfo" not in kwargs and "startupinfo" in _extra:
            kwargs["startupinfo"] = _extra["startupinfo"]
        if "creationflags" in _extra:
            flags = int(kwargs.get("creationflags", 0))
            kwargs["creationflags"] = flags | int(_extra["creationflags"])
        return _orig_popen(*args, **kwargs)

    subprocess.Popen = _popen  # type: ignore[method-assign]
    subprocess._slysh_no_console_patched = True


def subprocess_no_console_kwargs() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def terminate_process_tree(proc: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """Stop a child process and its descendants (engine, yt-dlp, etc.)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            **subprocess_no_console_kwargs(),
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)
