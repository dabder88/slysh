"""Queue audio blocks out of PortAudio / WASAPI callbacks."""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np

log = logging.getLogger(__name__)


class AudioIngestOverflowError(RuntimeError):
    pass


class AudioIngestQueue:
    def __init__(
        self,
        handler: Callable[[np.ndarray], None],
        *,
        max_blocks: int = 64,
        name: str = "audio-ingest",
    ) -> None:
        self._handler = handler
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=max_blocks)
        self._overflow = False
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
            self._overflow = True
            log.error("audio ingest queue full (%s)", self._thread.name)

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
