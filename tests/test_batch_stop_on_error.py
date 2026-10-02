"""Wave A4: on_error=stop pauses file batch and skips remaining jobs."""
from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest

from slysh.api import create_ui_app, _run_file_asr_job
from slysh.batch_runner import get_runner, start_batch
from slysh.db import Database
from slysh.models import BatchStatus, JobKind, JobStatus


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 800)


def test_file_batch_on_error_stop_pauses_after_failure(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    ok_wav = tmp_path / "ok.wav"
    _tiny_wav(ok_wav)
    missing = str(tmp_path / "gone.wav")

    batch_id = db.create_batch(
        "stop-test",
        {"on_error": "stop", "skip_completed": False},
    )
    job_ok = db.create_job(JobKind.FILE, str(ok_wav), batch_id=batch_id)
    job_bad = db.create_job(JobKind.FILE, missing, batch_id=batch_id)
    job_wait = db.create_job(JobKind.FILE, str(ok_wav), batch_id=batch_id)

    calls: list[int] = []

    def fake_run(_app, _db, job_id, _path):
        calls.append(job_id)
        _db.set_status(job_id, JobStatus.COMPLETED)

    start_batch(
        app,
        db,
        batch_id,
        run_file_job=fake_run,
        ensure_engine=lambda _a: "http://127.0.0.1:9",
        run_engine_job=lambda *_a: None,
        engine_cancel=lambda _u: None,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with get_runner(app).lock:
            if get_runner(app).batch_id is None:
                break
        time.sleep(0.05)

    batch = db.get_batch(batch_id)
    assert batch["status"] == BatchStatus.PAUSED.value
    assert job_ok in calls
    assert job_bad not in calls
    assert job_wait not in calls
    runner = get_runner(app)
    assert runner.summary is not None
    assert runner.summary.get("pause_reason") == "on_error_stop"
    assert runner.summary.get("failed", 0) >= 1


def test_file_batch_on_error_continue_marks_completed_with_errors(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    ok_wav = tmp_path / "ok.wav"
    _tiny_wav(ok_wav)
    missing = str(tmp_path / "missing.wav")

    batch_id = db.create_batch(
        "continue-test",
        {"on_error": "continue", "skip_completed": False},
    )
    db.create_job(JobKind.FILE, str(ok_wav), batch_id=batch_id)
    db.create_job(JobKind.FILE, missing, batch_id=batch_id)

    def fake_run(_app, _db, job_id, _path):
        _db.set_status(job_id, JobStatus.COMPLETED)

    start_batch(
        app,
        db,
        batch_id,
        run_file_job=fake_run,
        ensure_engine=lambda _a: "http://127.0.0.1:9",
        run_engine_job=lambda *_a: None,
        engine_cancel=lambda _u: None,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with get_runner(app).lock:
            if get_runner(app).batch_id is None:
                break
        time.sleep(0.05)

    assert db.get_batch(batch_id)["status"] == BatchStatus.COMPLETED_WITH_ERRORS.value
