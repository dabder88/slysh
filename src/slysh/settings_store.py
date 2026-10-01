"""Atomic read/write for JSON settings files."""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    return load_json_resilient(path, default)


def load_json_resilient(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    default = dict(default if default is not None else {})
    path = Path(path)
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        if not candidate.is_file():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logging.warning("settings read failed for %s: %s", candidate, exc)
            continue
        if isinstance(raw, dict):
            if candidate != path:
                logging.warning("settings restored from backup %s", candidate)
            return raw
    return default


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    if path.is_file():
        try:
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            logging.debug("settings backup skipped", exc_info=True)
    os.replace(tmp, path)


def save_json(path: Path, data: dict[str, Any]) -> None:
    with _lock:
        _atomic_write(Path(path), data)


def mutate_json(
    path: Path,
    mutator: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    path = Path(path)
    with _lock:
        data = load_json_resilient(path)
        mutator(data)
        _atomic_write(path, data)
        return dict(data)
