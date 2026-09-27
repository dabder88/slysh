from __future__ import annotations

from pathlib import Path

MEDIA_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
    ".mp4",
    ".mkv",
    ".avi",
}


def _is_media_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS


def scan_folder(path: str | Path, recursive: bool) -> list[str]:
    root = Path(path)
    if not root.is_dir():
        return []
    found: list[str] = []
    iterator = root.rglob("*") if recursive else root.glob("*")
    for item in iterator:
        if _is_media_file(item):
            found.append(str(item.resolve()))
    return sorted(set(found))


def scan_paths(paths: list[str], recursive: bool) -> list[str]:
    found: list[str] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        if path.is_dir():
            found.extend(scan_folder(path, recursive))
        elif _is_media_file(path):
            found.append(str(path.resolve()))
    return sorted(set(found))
