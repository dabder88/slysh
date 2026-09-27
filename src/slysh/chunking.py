from __future__ import annotations
import os
import numpy as np
from slysh.models import Segment

SAMPLE_RATE = 16000
CHUNK_SECONDS = 20
MIN_CHUNK_SECONDS = 1.0
MIN_CHUNK_SAMPLES = int(SAMPLE_RATE * MIN_CHUNK_SECONDS)
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS
LIVE_CHUNK_SECONDS = float(os.environ.get("GIGAAM_LIVE_CHUNK_SECONDS", "10"))
LIVE_CHUNK_SAMPLES = int(SAMPLE_RATE * LIVE_CHUNK_SECONDS)

def slice_chunks(audio: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """Yield (chunk_start_seconds, pcm) for each usable chunk."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    out: list[tuple[int, np.ndarray]] = []
    for start in range(0, len(audio), CHUNK_SAMPLES):
        piece = audio[start : start + CHUNK_SAMPLES]
        if len(piece) < MIN_CHUNK_SAMPLES:
            continue
        out.append((start // SAMPLE_RATE, piece))
    return out

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
    pcm = np.asarray(audio, dtype=np.float32).reshape(-1)
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
