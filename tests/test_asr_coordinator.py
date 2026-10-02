from __future__ import annotations

from types import SimpleNamespace

from slysh.asr_coordinator import (
    AsrCoordinator,
    job_run_active,
    job_run_id,
    pump_local_queued,
    pump_remote_queued,
)
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_coordinator_single_local_slot(tmp_path) -> None:
    coord = AsrCoordinator()
    assert coord.try_begin_local(1)
    assert not coord.try_begin_local(2)
    assert coord.local_job_id() == 1
    coord.end_local(1)
    assert coord.local_job_id() is None
    assert coord.try_begin_local(2)


def test_coordinator_single_remote_slot() -> None:
    coord = AsrCoordinator()
    assert coord.try_begin_remote(10)
    assert not coord.try_begin_remote(11)
    coord.end_remote(10)
    assert coord.try_begin_remote(11)


def test_job_run_active_respects_run_id_and_cancel(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, "a.mp3")
    db.begin_transcription(job_id)
    rid = job_run_id(db, job_id)
    assert job_run_active(db, job_id, rid)
    db.begin_transcription(job_id)
    assert not job_run_active(db, job_id, rid)
    new_rid = job_run_id(db, job_id)
    assert job_run_active(db, job_id, new_rid)
    db.set_status(job_id, JobStatus.CANCELLED)
    assert not job_run_active(db, job_id, new_rid)


def test_pump_local_skips_when_slot_busy(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = SimpleNamespace(state=SimpleNamespace(asr_coordinator=AsrCoordinator()))
    coord = app.state.asr_coordinator
    j1 = db.create_job(JobKind.FILE, "a.wav")
    db.begin_transcription(j1)
    coord.try_begin_local(j1)
    started: list[int] = []

    def start_engine(_app, _db, job_id: int, _path: str) -> None:
        started.append(job_id)

    pump_local_queued(
        app,
        db,
        is_youtube_job=lambda _j: False,
        is_remote_model=lambda: False,
        start_engine_job=start_engine,
    )
    assert started == []
    coord.end_local(j1)
    pump_local_queued(
        app,
        db,
        is_youtube_job=lambda _j: False,
        is_remote_model=lambda: False,
        start_engine_job=start_engine,
    )
    assert started == [j1]


def test_pump_remote_skips_when_slot_busy(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = SimpleNamespace(state=SimpleNamespace(asr_coordinator=AsrCoordinator()))
    coord = app.state.asr_coordinator
    j1 = db.create_job(JobKind.FILE, "a.wav")
    db.begin_transcription(j1)
    coord.try_begin_remote(j1)
    started: list[int] = []

    def start_remote(_app, _db, job_id: int, _path: str) -> None:
        started.append(job_id)

    pump_remote_queued(
        app,
        db,
        is_youtube_job=lambda _j: False,
        is_remote_model=lambda: True,
        start_remote_job=start_remote,
    )
    assert started == []
    coord.end_remote(j1)
    pump_remote_queued(
        app,
        db,
        is_youtube_job=lambda _j: False,
        is_remote_model=lambda: True,
        start_remote_job=start_remote,
    )
    assert started == [j1]
