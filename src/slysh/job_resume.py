from __future__ import annotations

import numpy as np

from slysh.chunking import SAMPLE_RATE
from slysh.models import JobStatus, Segment


def resume_ms_from_segments(segments: list[Segment]) -> int | None:
    if not segments:
        return None
    return max(int(seg.end_ms) for seg in segments)


def should_resume_file_job(status: str | None, segments: list[Segment]) -> bool:
    if status not in (JobStatus.CANCELLED.value, JobStatus.FAILED.value):
        return False
    return resume_ms_from_segments(segments) is not None


def apply_pcm_resume_trim(
    pcm: np.ndarray,
    offset_ms: int,
    resume_ms: int | None,
) -> tuple[np.ndarray, int]:
    """Trim decoded PCM so ASR continues after the last segment end."""
    base_offset = int(offset_ms or 0)
    if resume_ms is None:
        return pcm, base_offset
    trim_ms = max(0, int(resume_ms) - base_offset)
    if trim_ms <= 0:
        return pcm, base_offset
    trim_samples = int(trim_ms * SAMPLE_RATE / 1000)
    if trim_samples <= 0:
        return pcm, base_offset
    if trim_samples >= len(pcm):
        return pcm[:0], base_offset + trim_ms
    return pcm[trim_samples:], base_offset + trim_ms


def effective_transcribe_start_ms(
    range_start_ms: int | None,
    resume_ms: int | None,
) -> int | None:
    if resume_ms is None:
        return range_start_ms
    start = int(range_start_ms or 0)
    return max(start, int(resume_ms))


def progress_baseline_fraction(
    total_samples: int,
    offset_ms: int,
    resume_ms: int | None,
) -> float:
    """Share of the ranged PCM already transcribed (before resume trim)."""
    if resume_ms is None or total_samples <= 0:
        return 0.0
    total_ms = total_samples * 1000.0 / SAMPLE_RATE
    if total_ms <= 0:
        return 0.0
    done_ms = max(0.0, float(int(resume_ms) - int(offset_ms or 0)))
    return min(1.0, max(0.0, done_ms / total_ms))


def progress_baseline_for_remote(
    job: dict,
    effective_start_ms: int | None,
    duration_s: float | None,
) -> float:
    range_start = job.get("range_start_ms")
    range_end = job.get("range_end_ms")
    start = int(effective_start_ms if effective_start_ms is not None else (range_start or 0))
    if range_end is not None and range_start is not None:
        span = int(range_end) - int(range_start)
        if span > 0:
            return min(1.0, max(0.0, (start - int(range_start)) / span))
    if duration_s and duration_s > 0 and effective_start_ms is not None:
        return min(1.0, max(0.0, int(effective_start_ms) / (duration_s * 1000.0)))
    return 0.0


def map_transcribe_pass_progress(baseline: float, pass_value: float) -> float:
    """Map per-pass chunk progress (0..1) to jobs.progress (0..1)."""
    if pass_value >= 1.0:
        return 1.0
    base = min(1.0, max(0.0, float(baseline)))
    chunk = min(1.0, max(0.0, float(pass_value)))
    combined = base + (1.0 - base) * chunk
    return 0.01 + 0.99 * combined
