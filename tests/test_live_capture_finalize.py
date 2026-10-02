"""Wave A8: live/meeting stop must not mark job completed when ASR failed."""
from __future__ import annotations

from slysh.api import _finalize_capture_job
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_finalize_failed_when_state_error(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.LIVE, str(tmp_path / "live.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    _finalize_capture_job(db, {"error": "ASR boom"}, job_id)
    job = db.get_job(job_id) or {}
    assert job["status"] == JobStatus.FAILED.value
    assert "ASR boom" in str(job.get("error_text") or "")


def test_finalize_failed_when_error_text_without_state(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.MEETING, str(tmp_path / "meet.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    db.set_error(job_id, "chunk failed")
    _finalize_capture_job(db, {}, job_id)
    assert (db.get_job(job_id) or {})["status"] == JobStatus.FAILED.value


def test_finalize_completed_when_clean(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.LIVE, str(tmp_path / "live.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    _finalize_capture_job(db, {}, job_id)
    job = db.get_job(job_id) or {}
    assert job["status"] == JobStatus.COMPLETED.value
    assert float(job.get("progress") or 0) >= 1.0
