from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from slysh.paths import logs_dir

_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3

_WEBVIEW_NOISE = (
    "AliceBlue",
    "AntiqueWhite",
    "Empty.Empty",
    "maximum recursion depth",
    "CoreWebView2",
)


class _DropWebviewNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(token in msg for token in _WEBVIEW_NOISE)


def setup_logging() -> None:
    log_path = logs_dir() / "app.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = str(log_path.resolve())
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            existing = Path(getattr(handler, "baseFilename", "")).resolve()
            if str(existing) == target:
                return
    handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(_DropWebviewNoise())
    root.addHandler(handler)
    logging.getLogger("pywebview").addFilter(_DropWebviewNoise())
