from __future__ import annotations

import os
from collections.abc import Iterator

import numpy as np

from slysh.models import Segment

SAMPLE_RATE = 16000
CHUNK_SECONDS = 20
MIN_CHUNK_SECONDS = 1.0
MIN_CHUNK_SAMPLES = int(SAMPLE_RATE * MIN_CHUNK_SECONDS)
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS
LIVE_CHUNK_SECONDS = float(os.environ.get("GIGAAM_LIVE_CHUNK_SECONDS", "20"))
LIVE_CHUNK_SAMPLES = int(SAMPLE_RATE * LIVE_CHUNK_SECONDS)
MAX_LIVE_CHUNK_SECONDS = 60.0
WHISPER_LIVE_CHUNK_SECONDS_DEFAULT = 5.0
REMOTE_LIVE_CHUNK_SECONDS_DEFAULT = 20.0


def _clamp_live_chunk_seconds(value: float) -> float:
    return max(MIN_CHUNK_SECONDS, min(MAX_LIVE_CHUNK_SECONDS, float(value)))


def live_chunk_seconds_for_backend(backend: str) -> float:
    """Live/meeting ASR window length; fixed for the session at start."""
    key = (backend or "").strip().lower()
    if key == "whisper":
        raw = os.environ.get(
            "WHISPER_LIVE_CHUNK_SECONDS",
            str(WHISPER_LIVE_CHUNK_SECONDS_DEFAULT),
        )
        return _clamp_live_chunk_seconds(float(raw))
    if key == "gigaam":
        return _clamp_live_chunk_seconds(
            float(os.environ.get("GIGAAM_LIVE_CHUNK_SECONDS", "20"))
        )
    return _clamp_live_chunk_seconds(REMOTE_LIVE_CHUNK_SECONDS_DEFAULT)


def live_chunk_samples_for_backend(backend: str) -> int:
    return int(SAMPLE_RATE * live_chunk_seconds_for_backend(backend))


def count_pcm_chunks(n_samples: int) -> int:
    if n_samples <= 0:
        return 0
    count = 0
    for start in range(0, n_samples, CHUNK_SAMPLES):
        if start < n_samples:
            count += 1
    return count


def iter_pcm_chunk_windows(
    audio: np.ndarray,
) -> Iterator[tuple[int, np.ndarray]]:
    """Window over PCM without building a list of all chunks (R10)."""
    pcm = np.asarray(audio, dtype=np.float32, copy=False).reshape(-1)
    for start in range(0, len(pcm), CHUNK_SAMPLES):
        piece = pcm[start : start + CHUNK_SAMPLES]
        if len(piece) == 0:
            continue
        yield start // SAMPLE_RATE, piece


def slice_chunks(audio: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """Return (chunk_start_seconds, pcm) for each usable chunk."""
    return list(iter_pcm_chunk_windows(audio))

def offset_segments(
    segments: list[Segment],
    chunk_start_seconds: int = 0,
    start_ms: int | None = None,
) -> list[Segment]:
    delta = int(start_ms) if start_ms is not None else chunk_start_seconds * 1000
    return [
        Segment(
            start_ms=s.start_ms + delta,
            end_ms=s.end_ms + delta,
            text=s.text,
            speaker=s.speaker,
        )
        for s in segments
    ]


def slice_pcm_range(
    audio: np.ndarray,
    start_ms: int | None = None,
    end_ms: int | None = None,
    sample_rate: int = SAMPLE_RATE,
) -> tuple[np.ndarray, int]:
    pcm = np.asarray(audio, dtype=np.float32, copy=False).reshape(-1)
    if start_ms is None and end_ms is None:
        return pcm, 0
    total = len(pcm)
    start = 0 if start_ms is None else max(0, int(start_ms))
    i0 = min(total, int(start * sample_rate / 1000))
    if end_ms is None:
        i1 = total
    else:
        i1 = min(total, int(max(0, int(end_ms)) * sample_rate / 1000))
    if i1 < i0:
        i1 = i0
    offset = 0 if start_ms is None else start
    if i0 == 0 and i1 == total:
        return pcm, offset if start_ms else 0
    return pcm[i0:i1], offset
