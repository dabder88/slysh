"""Atomic read/write for JSON settings files."""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    default = default if default is not None else {}
    if not path.is_file():
        return dict(default)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("settings read failed for %s: %s", path, exc)
        return dict(default)
    return raw if isinstance(raw, dict) else dict(default)


def save_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with _lock:
        tmp.write_text(payload, encoding="utf-8")
        if path.is_file():
            try:
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                logging.debug("settings backup skipped", exc_info=True)
        os.replace(tmp, path)
