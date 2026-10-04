from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.speakers import (
    SPEAKER_CANCELLED_MESSAGE,
    FakeSpeakersBackend,
    SpeakerCancelledError,
    assign_speakers,
)


def test_cancel_clears_speaker_running_immediately(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\audio.wav")
    db.set_status(job_id, JobStatus.COMPLETED)
    app = create_ui_app(db=db, engine=None)
    app.state.speaker_jobs[job_id] = "running"
    app.state.speaker_started[job_id] = time.monotonic()
    app.state.speaker_cancels[job_id] = threading.Event()
    client = TestClient(app)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["speakers_running"] is False
    assert payload.get("speakers_error") == SPEAKER_CANCELLED_MESSAGE


def test_assign_speakers_restores_segments_when_cancelled_after_label(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\audio.wav")
    db.replace_segments(job_id, [Segment(0, 1000, "hello", speaker=None)])
    cancel = threading.Event()

    class LabelThenCancelBackend:
        def label(self, source_path, segments, *, cancelled=None):
            cancel.set()
            return [
                Segment(s.start_ms, s.end_ms, s.text, speaker="SPEAKER_00")
                for s in segments
            ]

    try:
        assign_speakers(
            db,
            job_id,
            LabelThenCancelBackend(),
            cancelled=cancel.is_set,
        )
        raise AssertionError("expected SpeakerCancelledError")
    except SpeakerCancelledError:
        pass
    segs = db.list_segments(job_id)
    assert len(segs) == 1
    assert segs[0].text == "hello"
    assert segs[0].speaker is None


def test_assign_speakers_keeps_user_edit_on_backend_error(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\audio.wav")
    db.replace_segments(job_id, [Segment(0, 1000, "OLD", speaker=None)])

    class FailAfterUserEdit:
        def label(self, source_path, segments, *, cancelled=None):
            db.replace_segments(job_id, [Segment(0, 1000, "USER EDIT", speaker=None)])
            raise RuntimeError("diarization failed")

    try:
        assign_speakers(db, job_id, FailAfterUserEdit())
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    segs = db.list_segments(job_id)
    assert len(segs) == 1
    assert segs[0].text == "USER EDIT"


def test_assign_speakers_fake_respects_cancel_before_label(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\audio.wav")
    db.replace_segments(job_id, [Segment(0, 500, "x")])
    cancel = threading.Event()
    cancel.set()
    try:
        assign_speakers(
            db,
            job_id,
            FakeSpeakersBackend(),
            cancelled=cancel.is_set,
        )
        raise AssertionError("expected SpeakerCancelledError")
    except SpeakerCancelledError:
        pass
