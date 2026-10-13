from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from slysh.models import JobKind, Segment

if TYPE_CHECKING:
    from slysh.db import Database


def _duration_from_segment_end_ms(end_ms: int | None) -> float | None:
    if end_ms is None or end_ms <= 0:
        return None
    return end_ms / 1000.0


def _duration_from_segments(segments: list[Segment]) -> float | None:
    if not segments:
        return None
    return _duration_from_segment_end_ms(max(int(seg.end_ms) for seg in segments))


def job_media_duration_s(
    job: dict,
    *,
    segments: list[Segment] | None = None,
    db: Database | None = None,
    allow_file_probe: bool = False,
) -> float | None:
    """Recording length in seconds (not wall-clock transcribe time)."""
    stored = job.get("media_duration_s")
    if stored is not None:
        try:
            value = float(stored)
        except (TypeError, ValueError):
            value = None
        if value is not None and value > 0:
            return value

    if str(job.get("kind") or "") == JobKind.YOUTUBE.value:
        youtube = job.get("youtube") or {}
        yt_dur = youtube.get("duration_s")
        if yt_dur is not None:
            try:
                value = float(yt_dur)
            except (TypeError, ValueError):
                value = None
            if value is not None and value > 0:
                return value

    range_start = job.get("range_start_ms")
    range_end = job.get("range_end_ms")
    if range_start is not None and range_end is not None:
        span = int(range_end) - int(range_start)
        if span > 0:
            return span / 1000.0

    if segments:
        from_segments = _duration_from_segments(segments)
        if from_segments is not None:
            return from_segments

    segment_max = job.get("segment_max_end_ms")
    if segment_max is not None:
        from_max = _duration_from_segment_end_ms(int(segment_max))
        if from_max is not None:
            return from_max

    if not allow_file_probe:
        return None

    source = str(job.get("source_path") or "").strip()
    kind = str(job.get("kind") or "")
    if source and kind != JobKind.YOUTUBE.value:
        try:
            from slysh.decode import media_duration_ms

            ms = media_duration_ms(source)
            if ms > 0:
                return ms / 1000.0
        except Exception:
            logging.debug("media duration probe failed for job %s", job.get("id"), exc_info=True)
    return None


def refresh_media_duration(db: Database, job_id: int) -> None:
    job = db.get_job(job_id)
    if job is None:
        return
    segments = db.list_segments(job_id)
    payload = dict(job)
    if str(payload.get("kind") or "") == JobKind.YOUTUBE.value:
        from slysh.youtube_ingest import attach_youtube_video

        attach_youtube_video(payload, segments, db=db)
    seconds = job_media_duration_s(
        payload, segments=segments, db=db, allow_file_probe=True
    )
    if seconds is not None:
        db.set_media_duration_s(job_id, seconds)
