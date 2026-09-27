from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


NEED_FULL_PATH_MESSAGE = (
    "Нет полного пути к файлу «{name}». "
    "Нажмите «Открыть» и выберите файл в диалоге."
)
FILE_NOT_FOUND_MESSAGE = "Файл не найден: {path}"
EMPTY_PATH_MESSAGE = "Путь к файлу пустой."


def normalize_source_path(raw: str) -> Path:
    """Turn a UI/drop string into a filesystem path (no existence check)."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError(EMPTY_PATH_MESSAGE)
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        local = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc.lower() not in ("", "localhost"):
            local = f"//{parsed.netloc}{local}"
        if os.name == "nt" and len(local) >= 3 and local[0] == "/" and local[2] == ":":
            local = local[1:]
        text = local.replace("/", os.sep) if os.name == "nt" else local
    return Path(text).expanduser()


def _looks_like_basename(path: Path) -> bool:
    if not path.is_absolute():
        return True
    return len(path.parts) <= 1


def require_existing_file(raw: str) -> Path:
    path = normalize_source_path(raw)
    candidate = path if path.is_absolute() else Path.cwd() / path
    if candidate.is_file():
        return candidate.resolve()
    if _looks_like_basename(path):
        raise ValueError(NEED_FULL_PATH_MESSAGE.format(name=path.name or raw))
    raise ValueError(FILE_NOT_FOUND_MESSAGE.format(path=path))
