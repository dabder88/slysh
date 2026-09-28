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


def resolve_open_target(path: str) -> Path:
    """Resolve a path for open/reveal; tolerate renames in the parent folder."""
    target = Path(path).expanduser()
    if target.exists():
        return target
    parent = target.parent
    if not parent.is_dir():
        raise FileNotFoundError(str(target))
    suffix = target.suffix.lower()
    stem = target.stem
    if suffix:
        candidates = [
            p
            for p in parent.iterdir()
            if p.is_file() and p.suffix.lower() == suffix
        ]
        by_stem = [p for p in candidates if p.stem == stem]
        if len(by_stem) == 1:
            return by_stem[0]
        if len(candidates) == 1:
            return candidates[0]
    return parent


def windows_explorer_reveal_args(path: str | Path) -> list[str]:
    """Explorer needs `/select,` and the path as two argv items.

    Glueing them (`/select,C:\\My files\\a.srt`) makes Explorer ignore the
    path and open a default folder instead.
    """
    return ["explorer", "/select,", os.path.normpath(str(path))]


def _launch_explorer(args: list[str]) -> None:
    """Start Explorer without CREATE_NO_WINDOW (GUI must stay visible)."""
    subprocess.Popen(args)


def _open_folder(folder: Path) -> None:
    if sys.platform == "win32":
        _launch_explorer(["explorer", os.path.normpath(str(folder))])
        return
    subprocess.Popen(["xdg-open", str(folder)])


def open_file(path: str) -> None:
    target = resolve_open_target(path)
    if target.is_dir():
        _open_folder(target)
        return
    if sys.platform == "win32":
        os.startfile(str(target))  # noqa: S606
        return
    subprocess.Popen(["xdg-open", str(target)])


def reveal_in_folder(path: str) -> None:
    target = resolve_open_target(path)
    if target.is_dir():
        _open_folder(target)
        return
    if sys.platform == "win32":
        _launch_explorer(windows_explorer_reveal_args(target))
        return
    subprocess.Popen(["xdg-open", str(target.parent)])


def open_paths(paths: list[str], *, reveal: bool) -> dict:
    opened: list[str] = []
    missing: list[str] = []
    for raw in paths:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            if reveal:
                reveal_in_folder(text)
            else:
                open_file(text)
            opened.append(text)
        except (FileNotFoundError, OSError):
            missing.append(text)
    return {"opened": opened, "missing": missing}
