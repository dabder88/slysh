"""Watch engine /progress during long HTTP calls (R11)."""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar

from slysh.engine_client import EngineError, cancel, progress

T = TypeVar("T")

_ACTIVE_PHASES = frozenset({"starting", "decode", "asr", "speakers"})


def progress_stall_timeout_s() -> float:
    raw = (os.environ.get("SLYSH_ENGINE_PROGRESS_STALL_S") or "").strip()
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return 600.0


class EngineProgressStallError(EngineError):
    """Engine progress unchanged too long during a long operation."""


def run_with_progress_watch(
    base_url: str,
    operation: Callable[[], T],
    *,
    stall_timeout_s: float | None = None,
    poll_s: float = 2.0,
) -> T:
    """Run a blocking engine HTTP call; cancel if /progress stalls in an active phase."""
    stall = stall_timeout_s if stall_timeout_s is not None else progress_stall_timeout_s()
    last_signature: tuple[str, float] | None = None
    last_change = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future: Future[T] = pool.submit(operation)
        while not future.done():
            time.sleep(poll_s)
            try:
                info = progress(base_url)
            except Exception:
                continue
            phase = str(info.get("phase") or "")
            try:
                prog = float(info.get("progress") or 0)
            except (TypeError, ValueError):
                prog = 0.0
            signature = (phase, prog)
            if signature != last_signature:
                last_signature = signature
                last_change = time.monotonic()
            elif phase in _ACTIVE_PHASES and time.monotonic() - last_change >= stall:
                try:
                    cancel(base_url)
                except Exception:
                    pass
                raise EngineProgressStallError(
                    "Распознавание не отвечает (нет прогресса). Операция отменена."
                )
        return future.result()
