import threading
import time

import numpy as np

from slysh.audio_ingest import (
    AUDIO_INGEST_OVERFLOW_MESSAGE,
    AudioIngestQueue,
    notify_capture_overflow,
)


def test_ingest_delivers_blocks_to_handler():
    received: list[int] = []

    def handler(block: np.ndarray) -> None:
        received.append(int(block.size))

    q = AudioIngestQueue(handler, max_blocks=4, name="test-ingest")
    q.push(np.ones(8, dtype=np.float32))
    q.close()
    assert received == [8]


def test_ingest_overflow_invokes_callback_once():
    hits: list[str] = []
    gate = threading.Event()

    def blocking_handler(_block: np.ndarray) -> None:
        gate.wait()

    q = AudioIngestQueue(
        blocking_handler,
        max_blocks=1,
        name="test-overflow",
        on_overflow=lambda: hits.append("overflow"),
    )
    q.push(np.ones(1600, dtype=np.float32))
    time.sleep(0.05)
    q.push(np.ones(1600, dtype=np.float32))
    q.push(np.ones(1600, dtype=np.float32))
    deadline = time.monotonic() + 1.0
    while not q.overflowed and time.monotonic() < deadline:
        time.sleep(0.02)
    gate.set()
    assert q.overflowed
    assert hits == ["overflow"]
    q.close()


def test_notify_capture_overflow_sets_error_and_stop():
    stop = threading.Event()
    holder = {"error": None, "stop_event": stop}
    notify_capture_overflow(holder)
    assert holder["error"] == AUDIO_INGEST_OVERFLOW_MESSAGE
    assert stop.is_set()
