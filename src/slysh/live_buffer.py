from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from slysh.chunking import LIVE_CHUNK_SAMPLES, MIN_CHUNK_SAMPLES, SAMPLE_RATE


class LiveSession:
    def __init__(self, wav_path: str | Path) -> None:
        self.wav_path = Path(wav_path)
        self.wav_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._pending = np.zeros(0, dtype=np.float32)
        self._file = sf.SoundFile(
            str(self.wav_path),
            mode="w",
            samplerate=SAMPLE_RATE,
            channels=1,
            subtype="FLOAT",
        )

    def buffered_samples(self) -> int:
        with self._lock:
            return int(len(self._pending))

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
            self._pending = np.concatenate([self._pending, pcm])

    def take_ready_chunks(self) -> list[np.ndarray]:
        chunks: list[np.ndarray] = []
        with self._lock:
            while len(self._pending) >= LIVE_CHUNK_SAMPLES:
                chunks.append(self._pending[:LIVE_CHUNK_SAMPLES].copy())
                self._pending = self._pending[LIVE_CHUNK_SAMPLES:]
        return chunks

    def take_pending_tail(self) -> np.ndarray | None:
        """Transcribe-ready tail without closing the WAV (e.g. live pause)."""
        with self._lock:
            if self._file.closed:
                return None
            if len(self._pending) < MIN_CHUNK_SAMPLES:
                return None
            tail = self._pending.copy()
            self._pending = np.zeros(0, dtype=np.float32)
            return tail

    def flush(self) -> np.ndarray | None:
        with self._lock:
            if not self._file.closed:
                self._file.close()
            tail = self._pending
            self._pending = np.zeros(0, dtype=np.float32)
            if len(tail) >= MIN_CHUNK_SAMPLES:
                return tail
            return None
