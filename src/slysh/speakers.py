from __future__ import annotations

from typing import Callable, Protocol

from slysh.db import Database
from slysh.models import Segment

SPEAKER_CANCELLED_MESSAGE = "Остановлено пользователем"


class SpeakerCancelledError(Exception):
    """Raised when user cancels speaker diarization."""


class SpeakersBackend(Protocol):
    def label(self, source_path: str, segments: list[Segment]) -> list[Segment]: ...


class FakeSpeakersBackend:
    def label(self, source_path: str, segments: list[Segment]) -> list[Segment]:
        return [
            Segment(s.start_ms, s.end_ms, s.text, speaker="SPEAKER_00")
            for s in segments
        ]


def _copy_segments(segments: list[Segment]) -> list[Segment]:
    return [
        Segment(s.start_ms, s.end_ms, s.text, speaker=s.speaker)
        for s in segments
    ]


def assign_speakers(
    db: Database,
    job_id: int,
    backend: SpeakersBackend,
    *,
    source_path: str | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[Segment]:
    job = db.get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if cancelled and cancelled():
        raise SpeakerCancelledError()
    media_path = str(source_path or job.get("source_path") or "").strip()
    if not media_path:
        raise ValueError(f"job {job_id} has no media path for speaker diarization")
    snapshot = _copy_segments(db.list_segments(job_id))
    try:
        labeled = backend.label(media_path, _copy_segments(snapshot))
    except Exception:
        db.replace_segments(job_id, snapshot)
        raise
    db.replace_segments(job_id, labeled)
    return labeled
