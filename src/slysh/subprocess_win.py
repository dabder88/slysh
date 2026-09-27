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
