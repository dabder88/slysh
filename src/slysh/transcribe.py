from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np

from slysh.chunking import offset_segments, slice_chunks, slice_pcm_range
from slysh.models import Segment


class AsrBackend(Protocol):
    def transcribe_chunk(
        self, pcm, cancelled: Callable[[], bool]
    ) -> list[Segment]: ...


def transcribe_pcm_chunks(
    pcm: np.ndarray,
    *,
    transcribe_chunk_fn: Callable[[np.ndarray], list[Segment]],
    cancelled: Callable[[], bool],
    on_progress: Callable[[float], None] | None = None,
    on_segments: Callable[[list[Segment]], None] | None = None,
    start_ms_offset: int = 0,
) -> tuple[str, list[Segment]]:
    """Run ASR on fixed-size PCM chunks; invoke on_segments after each chunk."""
    chunks = slice_chunks(np.asarray(pcm, dtype=np.float32))
    n = len(chunks)
    if n == 0:
        if on_progress is not None:
            on_progress(1.0)
        return ("completed", [])
    segs: list[Segment] = []
    for i, (start_s, chunk_pcm) in enumerate(chunks):
        if cancelled():
            return ("cancelled", segs)
        chunk_segs = transcribe_chunk_fn(chunk_pcm)
        piece = offset_segments(chunk_segs, start_ms=start_ms_offset + start_s * 1000)
        segs.extend(piece)
        if on_segments is not None and piece:
            on_segments(piece)
        if on_progress is not None:
            on_progress((i + 1) / n)
    if cancelled():
        return ("cancelled", segs)
    return ("completed", segs)


class FakeAsrBackend:
    def transcribe_chunk(self, pcm, cancelled: Callable[[], bool]) -> list[Segment]:
        if cancelled():
            return []
        return [Segment(0, 500, "ок")]


class FilePipeline:
    def __init__(self, backend: AsrBackend) -> None:
        self.backend = backend
        self.decode: Callable[[str], object] | None = None

    def transcribe(
        self,
        path: str,
        cancelled: Callable[[], bool],
        on_progress: Callable[[float], None] | None = None,
        decode: Callable[[str], object] | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> tuple[str, list[Segment]]:
        decode_fn = decode or self.decode
        if decode_fn is None:
            raise RuntimeError("decode callable is not set")
        pcm = decode_fn(path)
        pcm, offset_ms = slice_pcm_range(pcm, start_ms, end_ms)
        transcribe_file = getattr(self.backend, "transcribe_file", None)
        if callable(transcribe_file):
            segs = transcribe_file(pcm, cancelled, on_progress)
            if offset_ms:
                segs = offset_segments(segs, start_ms=offset_ms)
            if cancelled():
                return ("cancelled", segs)
            return ("completed", segs)
        chunks = slice_chunks(pcm)
        n = len(chunks)
        segs: list[Segment] = []
        for i, (start_s, chunk_pcm) in enumerate(chunks):
            if cancelled():
                return ("cancelled", segs)
            chunk_segs = self.backend.transcribe_chunk(chunk_pcm, cancelled)
            segs.extend(
                offset_segments(chunk_segs, start_ms=offset_ms + start_s * 1000)
            )
            if on_progress is not None and n:
                on_progress((i + 1) / n)
        return ("completed", segs)
