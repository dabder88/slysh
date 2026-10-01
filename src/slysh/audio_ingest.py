"""Queue audio blocks out of PortAudio / WASAPI callbacks."""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np

log = logging.getLogger(__name__)

AUDIO_INGEST_OVERFLOW_MESSAGE = (
    "Переполнена очередь аудио; запись остановлена, сохранена доступная часть."
)


class AudioIngestOverflowError(RuntimeError):
    pass


def notify_capture_overflow(holder: dict) -> None:
    """Signal live/meeting capture state: stop worker and surface error in status."""
    if not holder.get("error"):
        holder["error"] = AUDIO_INGEST_OVERFLOW_MESSAGE
    stop = holder.get("stop_event")
    if stop is not None:
        stop.set()


class AudioIngestQueue:
    def __init__(
        self,
        handler: Callable[[np.ndarray], None],
        *,
        max_blocks: int = 64,
        name: str = "audio-ingest",
        on_overflow: Callable[[], None] | None = None,
    ) -> None:
        self._handler = handler
        self._on_overflow = on_overflow
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=max_blocks)
        self._overflow = False
        self._overflow_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    @property
    def overflowed(self) -> bool:
        return self._overflow

    def push(self, pcm: np.ndarray) -> None:
        if self._overflow:
            return
        block = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if block.size == 0:
            return
        try:
            self._queue.put_nowait(block.copy())
        except queue.Full:
            self._mark_overflow()

    def _mark_overflow(self) -> None:
        with self._overflow_lock:
            if self._overflow:
                return
            self._overflow = True
        log.error("audio ingest queue full (%s)", self._thread.name)
        if self._on_overflow is not None:
            try:
                self._on_overflow()
            except Exception:
                log.exception("audio ingest on_overflow failed")

    def close(self, *, timeout: float = 5.0) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._queue.put(None)
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                self._handler(item)
            except Exception:
                log.exception("audio ingest handler failed")
