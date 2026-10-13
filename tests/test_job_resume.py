import numpy as np
import pytest

from slysh.chunking import SAMPLE_RATE
from slysh.job_resume import (
    apply_pcm_resume_trim,
    effective_transcribe_start_ms,
    map_transcribe_pass_progress,
    progress_baseline_for_remote,
    progress_baseline_fraction,
    resume_ms_from_segments,
    should_resume_file_job,
)
from slysh.models import JobStatus, Segment


def test_resume_ms_from_segments_empty():
    assert resume_ms_from_segments([]) is None


def test_resume_ms_from_segments_max_end():
    segs = [Segment(0, 1000, "a"), Segment(5000, 8000, "b")]
    assert resume_ms_from_segments(segs) == 8000


def test_should_resume_file_job():
    segs = [Segment(0, 2000, "x")]
    assert should_resume_file_job(JobStatus.CANCELLED.value, segs)
    assert should_resume_file_job(JobStatus.FAILED.value, segs)
    assert not should_resume_file_job(JobStatus.COMPLETED.value, segs)
    assert not should_resume_file_job(JobStatus.CANCELLED.value, [])


def test_apply_pcm_resume_trim():
    pcm = np.ones(int(SAMPLE_RATE * 10), dtype=np.float32)
    trimmed, offset = apply_pcm_resume_trim(pcm, offset_ms=1000, resume_ms=5000)
    assert offset == 5000
    assert len(trimmed) == int(SAMPLE_RATE * 6)


def test_effective_transcribe_start_ms():
    assert effective_transcribe_start_ms(2000, 5000) == 5000
    assert effective_transcribe_start_ms(None, 3000) == 3000
    assert effective_transcribe_start_ms(1000, None) == 1000


def test_progress_baseline_fraction():
    ten_s = int(SAMPLE_RATE * 10)
    assert progress_baseline_fraction(ten_s, 0, None) == 0.0
    assert progress_baseline_fraction(ten_s, 0, 4000) == 0.4
    assert progress_baseline_fraction(ten_s, 1000, 5000) == 0.4


def test_map_transcribe_pass_progress():
    assert map_transcribe_pass_progress(0.0, 0.0) == 0.01
    assert map_transcribe_pass_progress(0.0, 1.0) == 1.0
    assert map_transcribe_pass_progress(0.4, 0.0) == pytest.approx(0.01 + 0.99 * 0.4)
    assert map_transcribe_pass_progress(0.4, 1.0) == 1.0
    mid = map_transcribe_pass_progress(0.4, 0.5)
    assert mid == pytest.approx(0.01 + 0.99 * 0.7)
    penultimate = map_transcribe_pass_progress(0.0, 99 / 100)
    assert penultimate < 1.0
    assert penultimate == pytest.approx(0.01 + 0.99 * 0.99)


def test_transcribe_pcm_chunks_finishes_at_full_progress():
    import numpy as np

    from slysh.chunking import CHUNK_SAMPLES
    from slysh.transcribe import transcribe_pcm_chunks

    pcm = np.zeros(CHUNK_SAMPLES * 2, dtype=np.float32)
    seen: list[float] = []

    def on_progress(value: float) -> None:
        seen.append(float(value))

    status, _ = transcribe_pcm_chunks(
        pcm,
        transcribe_chunk_fn=lambda _chunk: [],
        cancelled=lambda: False,
        on_progress=on_progress,
    )
    assert status == "completed"
    assert seen[-1] == 1.0


def test_progress_baseline_for_remote():
    job = {"range_start_ms": 0, "range_end_ms": 10_000}
    assert progress_baseline_for_remote(job, 4000, 20.0) == 0.4
    assert progress_baseline_for_remote(job, None, 20.0) == 0.0
    assert progress_baseline_for_remote({}, 5000, 10.0) == 0.5
