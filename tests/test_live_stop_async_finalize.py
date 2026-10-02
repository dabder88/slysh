"""Live stop returns before slow ASR finalize (plan 3.1)."""
from __future__ import annotations

import time

import numpy as np
from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.chunking import SAMPLE_RATE
from slysh.db import Database
from slysh.models import JobStatus


class _FakeStream:
    def __init__(self, **kwargs):
        pass

    def start(self):
        return None

    def stop(self):
        return None

    def close(self):
        return None


def test_live_stop_returns_before_slow_asr_finalize(tmp_path, monkeypatch):
    def slow_handle(app, db, pcm, *, capture_state=None):
        time.sleep(0.5)

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", slow_handle)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/live/start", json={})
    assert r.status_code == 200
    job_id = r.json()["id"]
    session = app.state.live["session"]
    # Sub-chunk tail only — worker does not ASR until stop finalizer runs.
    session.push(np.zeros(SAMPLE_RATE, np.float32))

    t0 = time.monotonic()
    stopped = client.post("/api/live/stop")
    elapsed = time.monotonic() - t0
    assert stopped.status_code == 200
    assert elapsed < 0.35
    assert (db.get_job(job_id) or {})["status"] == JobStatus.FINALIZING.value

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if (db.get_job(job_id) or {}).get("status") == JobStatus.COMPLETED.value:
            break
        time.sleep(0.02)
    assert (db.get_job(job_id) or {})["status"] == JobStatus.COMPLETED.value


def test_capture_finalizing_flag_while_finalize_runs(tmp_path, monkeypatch):
    started: list[int] = []

    def slow_handle(app, db, pcm, *, capture_state=None):
        started.append(1)
        time.sleep(0.4)

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", slow_handle)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/live/start", json={})
    job_id = r.json()["id"]
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    status = client.get("/api/live/status").json()
    assert status.get("capture_finalizing") is True
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job.get("capture_finalizing") is True
    assert job.get("status") == JobStatus.FINALIZING.value
    threads = getattr(app.state, "capture_finalize_threads", {})
    if threads.get(job_id):
        threads[job_id].join(timeout=2.0)
