import numpy as np
from slysh.chunking import SAMPLE_RATE, slice_chunks, offset_segments
from slysh.models import Segment


def test_skips_tail_shorter_than_one_second():
    audio = np.zeros(int(SAMPLE_RATE * 20.5), dtype=np.float32)
    chunks = list(slice_chunks(audio))
    assert len(chunks) == 1
    start, pcm = chunks[0]
    assert start == 0
    assert len(pcm) == SAMPLE_RATE * 20


def test_two_full_chunks():
    audio = np.zeros(SAMPLE_RATE * 40, dtype=np.float32)
    chunks = list(slice_chunks(audio))
    assert [s for s, _ in chunks] == [0, 20]


def test_offset_segments_adds_chunk_start():
    segs = [Segment(start_ms=100, end_ms=900, text="x")]
    out = offset_segments(segs, chunk_start_seconds=20)
    assert out[0].start_ms == 20100
    assert out[0].end_ms == 20900


def test_slice_pcm_range_keeps_full_audio_when_empty():
    from slysh.chunking import slice_pcm_range

    audio = np.arange(SAMPLE_RATE * 4, dtype=np.float32)
    sliced, offset = slice_pcm_range(audio, None, None)
    assert offset == 0
    assert len(sliced) == len(audio)


def test_slice_pcm_range_cuts_and_reports_offset():
    from slysh.chunking import slice_pcm_range

    audio = np.arange(SAMPLE_RATE * 5, dtype=np.float32)
    sliced, offset = slice_pcm_range(audio, 1000, 3000)
    assert offset == 1000
    assert len(sliced) == SAMPLE_RATE * 2


def test_offset_segments_start_ms():
    segs = [Segment(start_ms=100, end_ms=400, text="x")]
    out = offset_segments(segs, start_ms=1500)
    assert out[0].start_ms == 1600
    assert out[0].end_ms == 1900
