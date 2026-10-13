"""Intake-like queue: 3 orphans started, bulk pause/cancel must not run queued jobs."""
from __future__ import annotations

import time
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.asr_coordinator import job_run_active, job_run_id
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 400)


def _three_orphan_jobs(tmp_path: Path, db: Database) -> tuple[int, int, int]:
    ids: list[int] = []
    for name in ("a.wav", "b.wav", "c.wav"):
        wav = tmp_path / name
        _tiny_wav(wav)
        ids.append(db.create_job(JobKind.FILE, str(wav)))
    return ids[0], ids[1], ids[2]


def _wait_status(db: Database, job_id: int, status: str, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if (db.get_job(job_id) or {}).get("status") == status:
            return
        time.sleep(0.03)
    raise AssertionError(
        f"job {job_id} expected status {status}, got {(db.get_job(job_id) or {}).get('status')}"
    )


@pytest.fixture
def intake_queue_client(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_require_asr_ready", lambda: None)
    monkeypatch.setattr(api_mod, "_engine_status", lambda _app: "cpu")
    monkeypatch.setattr(api_mod, "_selected_asr_preflight_error", lambda: None)

    db = Database(tmp_path / "home" / "app.db")
    j1, j2, j3 = _three_orphan_jobs(tmp_path, db)
    engine_calls: list[int] = []

    def fake_run_engine(_db, _url: str, job_id: int, _path: str, **_kwargs) -> None:
        engine_calls.append(job_id)
        run_id = job_run_id(_db, job_id)
        _db.set_status(job_id, JobStatus.RUNNING)
        if job_id == j1:
            while job_run_active(_db, job_id, run_id):
                time.sleep(0.03)
            return
        _db.set_status(job_id, JobStatus.COMPLETED)

    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    app.state.engine_url = "http://127.0.0.1:9"

    with (
        patch.object(api_mod, "_run_engine_job", fake_run_engine),
        patch.object(api_mod, "engine_cancel", lambda _url: None),
    ):
        client = TestClient(app)
        yield client, db, j1, j2, j3, engine_calls


def _start_three_like_intake(client: TestClient, db: Database, j1: int, j2: int, j3: int) -> None:
    for jid in (j1, j2, j3):
        r = client.post(f"/api/jobs/{jid}/start")
        assert r.status_code == 200
    _wait_status(db, j1, JobStatus.RUNNING.value)
    assert (db.get_job(j2) or {})["status"] == JobStatus.QUEUED.value
    assert (db.get_job(j3) or {})["status"] == JobStatus.QUEUED.value


def test_intake_three_jobs_pause_orphans_does_not_start_queued(intake_queue_client):
    client, db, j1, j2, j3, engine_calls = intake_queue_client
    _start_three_like_intake(client, db, j1, j2, j3)
    assert engine_calls == [j1]

    r = client.post("/api/queue/pause-orphans")
    assert r.status_code == 200
    assert r.json().get("paused_count") == 3

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if all(
            (db.get_job(jid) or {}).get("status") == JobStatus.IDLE.value
            for jid in (j1, j2, j3)
        ):
            break
        time.sleep(0.05)
    else:
        statuses = {jid: (db.get_job(jid) or {}).get("status") for jid in (j1, j2, j3)}
        raise AssertionError(f"expected all idle after pause-orphans, got {statuses}")

    assert engine_calls == [j1], "queued jobs must not be started by pump after bulk pause"

    api_mod._pump_asr_queues(client.app, db)
    assert engine_calls == [j1], "explicit pump after pause must not start idle/former-queued jobs"


def test_intake_three_jobs_cancel_orphans_does_not_complete_queued(intake_queue_client):
    client, db, j1, j2, j3, engine_calls = intake_queue_client
    _start_three_like_intake(client, db, j1, j2, j3)
    assert engine_calls == [j1]

    r = client.post("/api/queue/cancel-orphans")
    assert r.status_code == 200
    assert r.json().get("cancelled_count") == 3

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        statuses = [ (db.get_job(jid) or {}).get("status") for jid in (j1, j2, j3) ]
        if all(s == JobStatus.CANCELLED.value for s in statuses):
            break
        time.sleep(0.05)
    else:
        raise AssertionError(
            f"expected all cancelled, got "
            f"j1={ (db.get_job(j1) or {}).get('status') } "
            f"j2={ (db.get_job(j2) or {}).get('status') } "
            f"j3={ (db.get_job(j3) or {}).get('status') }"
        )

    assert engine_calls == [j1], "cancel-orphans must not run queued transcriptions"
    assert not db.list_queued_jobs()

    api_mod._pump_asr_queues(client.app, db)
    assert engine_calls == [j1]
