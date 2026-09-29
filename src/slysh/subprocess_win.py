"""Windows subprocess helpers (hide console for GUI app)."""
from __future__ import annotations

import subprocess
import sys


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
