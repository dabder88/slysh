"""Wave C: capture finalize holds local ASR coordinator slot."""
from __future__ import annotations

import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import CAPTURE_FINALIZING_HINT, create_ui_app
from slysh.asr_coordinator import AsrCoordinator
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


def test_live_start_acquires_local_coordinator_slot(tmp_path, monkeypatch):
    db, app, client = _live_finalize_fixture(
        tmp_path,
        monkeypatch,
        lambda *a, **k: None,
    )
    coord: AsrCoordinator = app.state.asr_coordinator
    started = client.post("/api/live/start", json={})
    assert started.status_code == 200
    assert coord.local_job_id() == started.json()["id"]
    client.post("/api/live/stop")
    threads = getattr(app.state, "capture_finalize_threads", {}) or {}
    for t in list(threads.values()):
        t.join(timeout=3.0)
    assert coord.local_job_id() is None


def test_live_start_blocked_while_capture_finalize_busy(tmp_path, monkeypatch):
    held = threading.Event()
    released = threading.Event()

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=2.0)

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", slow_handle)
    monkeypatch.setattr(api_mod, "_capture_finalize_uses_local_engine", lambda app: True)
    monkeypatch.setattr(api_mod, "_require_asr_ready", lambda: None)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    coord: AsrCoordinator = app.state.asr_coordinator
    client = TestClient(app)
    started = client.post("/api/live/start", json={})
    assert started.status_code == 200, started.text
    session = app.state.live.get("session")
    assert session is not None
    session.push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    assert held.wait(timeout=2.0)
    assert coord.local_job_id() is not None
    r = client.post("/api/live/start", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == CAPTURE_FINALIZING_HINT
    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {})
    for t in list(threads.values()):
        t.join(timeout=3.0)
    assert coord.local_job_id() is None


def _live_finalize_fixture(
    tmp_path,
    monkeypatch,
    slow_handle,
    *,
    uses_local: bool = True,
    uses_remote: bool = False,
):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", slow_handle)
    monkeypatch.setattr(api_mod, "_capture_finalize_uses_local_engine", lambda app: uses_local)
    monkeypatch.setattr(api_mod, "_capture_finalize_uses_remote_engine", lambda app: uses_remote)
    monkeypatch.setattr(api_mod, "_require_asr_ready", lambda: None)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    return db, app, client


def test_cancel_job_during_capture_finalize_calls_engine_cancel(tmp_path, monkeypatch):
    held = threading.Event()
    released = threading.Event()
    cancels: list[str] = []

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=2.0)

    monkeypatch.setattr(api_mod, "engine_cancel", lambda url: cancels.append(url))
    db, app, client = _live_finalize_fixture(tmp_path, monkeypatch, slow_handle)
    app.state.engine_url = "http://engine.test"

    started = client.post("/api/live/start", json={})
    job_id = started.json()["id"]
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    assert held.wait(timeout=2.0)

    cancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancels == ["http://engine.test"]
    assert (db.get_job(job_id) or {})["status"] == JobStatus.CANCELLED.value

    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {})
    if threads.get(job_id):
        threads[job_id].join(timeout=3.0)


def test_remote_finalize_holds_remote_coordinator_slot(tmp_path, monkeypatch):
    held = threading.Event()
    released = threading.Event()

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=2.0)

    db, app, client = _live_finalize_fixture(
        tmp_path, monkeypatch, slow_handle, uses_local=False, uses_remote=True
    )
    coord: AsrCoordinator = app.state.asr_coordinator

    started = client.post("/api/live/start", json={})
    job_id = started.json()["id"]
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    assert held.wait(timeout=2.0)
    assert coord.remote_job_id() == job_id
    assert coord.local_job_id() is None

    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {})
    if threads.get(job_id):
        threads[job_id].join(timeout=3.0)
    assert coord.remote_job_id() is None


def test_meeting_start_blocked_while_capture_finalize_busy(tmp_path, monkeypatch):
    held = threading.Event()
    released = threading.Event()

    class _FakeCapture:
        def __init__(self, **kwargs):
            pass

        def start(self):
            return None

        def stop(self):
            return None

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=2.0)

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 3, "name": "Speakers"}])
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", slow_handle)
    monkeypatch.setattr(api_mod, "_capture_finalize_uses_local_engine", lambda app: True)
    monkeypatch.setattr(api_mod, "_require_asr_ready", lambda: None)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    started = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    assert started.status_code == 200
    job_id = started.json()["id"]
    app.state.meeting["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/meeting/stop")
    assert held.wait(timeout=2.0)
    blocked = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == CAPTURE_FINALIZING_HINT
    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {})
    if threads.get(job_id):
        threads[job_id].join(timeout=3.0)
