from __future__ import annotations

from typing import Callable, Protocol

from slysh.db import (
    Database,
    SegmentsRevisionConflictError,
    SegmentsSnapshot,
)
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


def _structure_key(snapshot: SegmentsSnapshot) -> tuple[tuple[int, int, int], ...]:
    return tuple((r.row_id, r.start_ms, r.end_ms) for r in snapshot.rows)


def _segments_for_backend(snapshot: SegmentsSnapshot) -> list[Segment]:
    return [
        Segment(r.start_ms, r.end_ms, r.text, speaker=r.speaker)
        for r in snapshot.rows
    ]


def _merge_speaker_labels(
    base: SegmentsSnapshot,
    current: SegmentsSnapshot,
    labeled: list[Segment],
) -> list[Segment]:
    if _structure_key(base) != _structure_key(current):
        raise SpeakerStructureChangedError("segment structure changed during diarization")
    if len(labeled) != len(current.rows):
        raise SpeakerStructureChangedError(
            f"segment count mismatch: {len(current.rows)} vs {len(labeled)}"
        )
    merged: list[Segment] = []
    for i, row in enumerate(current.rows):
        base_row = base.rows[i]
        if row.speaker != base_row.speaker:
            raise SpeakerStructureChangedError(
                "speaker binding changed during diarization"
            )
        lab = labeled[i]
        if row.start_ms != lab.start_ms or row.end_ms != lab.end_ms:
            raise SpeakerStructureChangedError(
                "labeled segment bounds do not match current structure"
            )
        merged.append(
            Segment(row.start_ms, row.end_ms, row.text, speaker=lab.speaker)
        )
    return merged


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
    base = db.get_segments_snapshot(job_id)
    try:
        labeled = backend.label(
            media_path,
            _copy_segments(_segments_for_backend(base)),
            cancelled=cancelled,
        )
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        current = db.get_segments_snapshot(job_id)
        merged = _merge_speaker_labels(base, current, labeled)
        db.replace_segments(job_id, merged, expected_revision=current.revision)
        return merged
    except SpeakerCancelledError:
        raise
    except SegmentsRevisionConflictError:
        raise
    except SpeakerStructureChangedError:
        raise
    except Exception:
        raise
