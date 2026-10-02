"""Wave C.2/C.4: run_id and idempotent POST /start while job is queued."""
from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.asr_coordinator import job_run_id
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_start_while_queued_keeps_run_id(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 100)
    job_id = db.create_job(JobKind.FILE, str(wav))
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    app.state.engine_url = "http://127.0.0.1:9"
    gate = threading.Event()

    def block_engine(_db, _url, jid: int, _path: str) -> None:
        gate.wait(timeout=5.0)
        _db.set_status(jid, JobStatus.COMPLETED)

    with (
        patch.object(api_mod, "_run_engine_job", block_engine),
        patch.object(api_mod, "_engine_status", lambda _app: "cpu"),
        patch.object(api_mod, "_selected_asr_preflight_error", lambda: None),
    ):
        client = TestClient(app)
        r1 = client.post(f"/api/jobs/{job_id}/start")
        assert r1.status_code == 200
        rid_after_first = job_run_id(db, job_id)
        assert rid_after_first >= 1
        assert (db.get_job(job_id) or {}).get("status") == JobStatus.QUEUED.value
        r2 = client.post(f"/api/jobs/{job_id}/start")
        assert r2.status_code == 200
        assert job_run_id(db, job_id) == rid_after_first
        gate.set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (db.get_job(job_id) or {}).get("status") == JobStatus.COMPLETED.value:
                break
            time.sleep(0.05)
        assert (db.get_job(job_id) or {}).get("status") == JobStatus.COMPLETED.value


def test_begin_transcription_increments_run_id(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, "a.wav")
    db.begin_transcription(job_id)
    first = job_run_id(db, job_id)
    db.begin_transcription(job_id)
    assert job_run_id(db, job_id) == first + 1
