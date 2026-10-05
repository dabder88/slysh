import numpy as np
from slysh.chunking import (
    CHUNK_SAMPLES,
    SAMPLE_RATE,
    count_pcm_chunks,
    iter_pcm_chunk_windows,
    offset_segments,
    slice_chunks,
)
from slysh.models import Segment


def test_count_pcm_chunks_matches_slice_chunks():
    audio = np.zeros(int(SAMPLE_RATE * 20.5), dtype=np.float32)
    assert count_pcm_chunks(len(audio)) == len(slice_chunks(audio))


def test_iter_pcm_chunk_windows_on_memmap(tmp_path):
    path = tmp_path / "pcm.f32"
    n = CHUNK_SAMPLES * 2 + 500
    mm = np.memmap(path, dtype=np.float32, mode="w+", shape=(n,))
    mm[:] = 0
    windows = list(iter_pcm_chunk_windows(mm))
    assert len(windows) == 3
    assert windows[0][0] == 0
    assert len(windows[0][1]) == CHUNK_SAMPLES
    assert len(windows[-1][1]) == 500


def test_keeps_tail_shorter_than_one_second():
    audio = np.zeros(int(SAMPLE_RATE * 20.5), dtype=np.float32)
    chunks = list(slice_chunks(audio))
    assert len(chunks) == 2
    assert chunks[0][0] == 0
    assert len(chunks[0][1]) == SAMPLE_RATE * 20
    assert chunks[1][0] == 20
    assert len(chunks[1][1]) == int(SAMPLE_RATE * 0.5)


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
