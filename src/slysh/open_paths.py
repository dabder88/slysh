from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def resolve_existing(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(str(target))
    return target


def windows_explorer_reveal_args(path: str | Path) -> list[str]:
    """Explorer needs `/select,` and the path as two argv items.

    Glueing them (`/select,C:\\My files\\a.srt`) makes Explorer ignore the
    path and open a default folder instead.
    """
    return ["explorer", "/select,", os.path.normpath(str(path))]


def open_file(path: str) -> None:
    target = resolve_existing(path)
    if sys.platform == "win32":
        os.startfile(str(target))  # noqa: S606
        return
    subprocess.Popen(["xdg-open", str(target)])


def reveal_in_folder(path: str) -> None:
    target = resolve_existing(path)
    if sys.platform == "win32":
        subprocess.Popen(windows_explorer_reveal_args(target))
        return
    folder = target if target.is_dir() else target.parent
    subprocess.Popen(["xdg-open", str(folder)])
