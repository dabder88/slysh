from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from slysh.chunking import LIVE_CHUNK_SAMPLES, SAMPLE_RATE

_DEFAULT_MAX_PENDING = 3 * LIVE_CHUNK_SAMPLES
LIVE_MAX_PENDING_SAMPLES = int(
    os.environ.get("SLYSH_LIVE_PENDING_MAX_SAMPLES", str(_DEFAULT_MAX_PENDING))
)


class LiveBufferOverflowError(RuntimeError):
    """RAM pending cap exceeded; full audio remains in the session WAV on disk."""


class LiveSession:
    def __init__(self, wav_path: str | Path) -> None:
        self.wav_path = Path(wav_path)
        self.wav_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        cap = max(LIVE_MAX_PENDING_SAMPLES, LIVE_CHUNK_SAMPLES)
        self._pending_cap = cap
        self._pending = np.zeros(cap, dtype=np.float32)
        self._pending_len = 0
        self._file = sf.SoundFile(
            str(self.wav_path),
            mode="w",
            samplerate=SAMPLE_RATE,
            channels=1,
            subtype="FLOAT",
        )

    def buffered_samples(self) -> int:
        with self._lock:
            return int(self._pending_len)

    def remaining_s(self) -> float:
        used = self.buffered_samples() % LIVE_CHUNK_SAMPLES
        return (LIVE_CHUNK_SAMPLES - used) / SAMPLE_RATE

    def push(self, samples: np.ndarray) -> None:
        pcm = np.asarray(samples, dtype=np.float32).reshape(-1)
        with self._lock:
            if self._file.closed:
                return
            if len(pcm) == 0:
                return
            self._file.write(pcm)
            self._file.flush()
            next_len = self._pending_len + len(pcm)
            if next_len > self._pending_cap:
                raise LiveBufferOverflowError(
                    "Буфер распознавания переполнен; запись на диск сохранена."
                )
            end = self._pending_len + len(pcm)
            self._pending[self._pending_len:end] = pcm
            self._pending_len = end

    def take_ready_chunks(self) -> list[np.ndarray]:
        chunks: list[np.ndarray] = []
        with self._lock:
            while self._pending_len >= LIVE_CHUNK_SAMPLES:
                chunks.append(self._pending[:LIVE_CHUNK_SAMPLES].copy())
                remain = self._pending_len - LIVE_CHUNK_SAMPLES
                if remain > 0:
                    self._pending[:remain] = self._pending[
                        LIVE_CHUNK_SAMPLES : self._pending_len
                    ]
                self._pending_len = remain
        return chunks

    def take_pending_tail(self) -> np.ndarray | None:
        """Transcribe-ready tail without closing the WAV (e.g. live pause)."""
        with self._lock:
            if self._file.closed:
                return None
            if self._pending_len <= 0:
                return None
            tail = self._pending[: self._pending_len].copy()
            self._pending_len = 0
            return tail

    def flush(self) -> np.ndarray | None:
        with self._lock:
            if not self._file.closed:
                self._file.close()
            if self._pending_len <= 0:
                return None
            tail = self._pending[: self._pending_len].copy()
            self._pending_len = 0
            return tail
