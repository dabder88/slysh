from __future__ import annotations

from typing import Callable, Protocol

from slysh.db import Database, SegmentsRevisionConflictError
from slysh.models import Segment

SPEAKER_CANCELLED_MESSAGE = "Остановлено пользователем"


class SpeakerCancelledError(Exception):
    """Raised when user cancels speaker diarization."""


class SpeakerStructureChangedError(Exception):
    """Diarization result does not match current segment structure."""


class SpeakersBackend(Protocol):
    def label(
        self,
        source_path: str,
        segments: list[Segment],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Segment]: ...


class FakeSpeakersBackend:
    def label(
        self,
        source_path: str,
        segments: list[Segment],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Segment]:
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        return [
            Segment(s.start_ms, s.end_ms, s.text, speaker="SPEAKER_00")
            for s in segments
        ]


def _copy_segments(segments: list[Segment]) -> list[Segment]:
    return [
        Segment(s.start_ms, s.end_ms, s.text, speaker=s.speaker)
        for s in segments
    ]


def _merge_speaker_labels(
    current: list[Segment],
    labeled: list[Segment],
) -> list[Segment]:
    if len(current) != len(labeled):
        raise SpeakerStructureChangedError(
            f"segment count mismatch: {len(current)} vs {len(labeled)}"
        )
    return [
        Segment(cur.start_ms, cur.end_ms, cur.text, speaker=lab.speaker)
        for cur, lab in zip(current, labeled, strict=True)
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
    base_revision = db.segments_revision(job_id)
    structure = _copy_segments(db.list_segments(job_id))
    try:
        labeled = backend.label(
            media_path,
            _copy_segments(structure),
            cancelled=cancelled,
        )
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        current = db.list_segments(job_id)
        merged = _merge_speaker_labels(current, labeled)
        revision = db.segments_revision(job_id)
        db.replace_segments(job_id, merged, expected_revision=revision)
        return merged
    except SpeakerCancelledError:
        raise
    except SegmentsRevisionConflictError:
        raise
    except Exception:
        if db.segments_revision(job_id) == base_revision:
            pass
        raise
