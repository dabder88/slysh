import numpy as np

from slysh.chunking import CHUNK_SAMPLES, SAMPLE_RATE
from slysh.models import Segment
from slysh.transcribe import transcribe_pcm_chunks


def test_transcribe_pcm_chunks_calls_on_segments():
    pcm = np.zeros(CHUNK_SAMPLES * 2, dtype=np.float32)
    seen: list[list[Segment]] = []

    def transcribe_chunk_fn(chunk_pcm):
        return [Segment(0, 100, f"len={len(chunk_pcm)}")]

    status, all_segs = transcribe_pcm_chunks(
        pcm,
        transcribe_chunk_fn=transcribe_chunk_fn,
        cancelled=lambda: False,
        on_segments=lambda piece: seen.append(piece),
    )
    assert status == "completed"
    assert len(seen) == 2
    assert len(all_segs) == 2
    assert all_segs[1].start_ms == 20_000


def test_transcribe_pcm_chunks_cancel_mid_loop():
    pcm = np.zeros(CHUNK_SAMPLES * 3, dtype=np.float32)
    n_calls = 0

    def transcribe_chunk_fn(_chunk_pcm):
        nonlocal n_calls
        n_calls += 1
        return [Segment(0, 100, "x")]

    cancelled = {"stop": False}

    def is_cancelled():
        return cancelled["stop"]

    status, segs = transcribe_pcm_chunks(
        pcm,
        transcribe_chunk_fn=transcribe_chunk_fn,
        cancelled=is_cancelled,
        on_segments=lambda _piece: cancelled.update({"stop": True}),
    )
    assert status == "cancelled"
    assert n_calls == 1
    assert len(segs) == 1


def test_transcribe_pcm_chunks_start_ms_offset():
    pcm = np.zeros(int(SAMPLE_RATE * 5), dtype=np.float32)

    def transcribe_chunk_fn(_chunk_pcm):
        return [Segment(0, 500, "a")]

    status, segs = transcribe_pcm_chunks(
        pcm,
        transcribe_chunk_fn=transcribe_chunk_fn,
        cancelled=lambda: False,
        start_ms_offset=3000,
    )
    assert status == "completed"
    assert segs[0].start_ms == 3000
