"""Targeted regressions from plan-fix wave A."""
from __future__ import annotations

import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from slysh import runtime_setup, updates
from slysh.api import create_ui_app
from slysh.db import Database
from slysh.engine_server import create_app
from slysh.models import JobKind, JobStatus, Segment


def test_install_repeat_start_does_not_deadlock(monkeypatch):
    monkeypatch.setattr(runtime_setup, "engine_packages_ok", lambda **_: False)
    with runtime_setup._lock:
        runtime_setup._install["running"] = True
    done = threading.Event()

    def second():
        runtime_setup.start_engine_install()
        done.set()

    threading.Thread(target=second).start()
    assert done.wait(timeout=2)


def test_updates_repeat_download_does_not_deadlock(monkeypatch):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    with updates._lock:
        updates._state.clear()
        updates._state.update(
            {
                "phase": "idle",
                "pending": {
                    "version": "9.9.9",
                    "download_url": "https://github.com/x/y.exe",
                    "size": 1,
                    "expected_sha256": "c" * 64,
                },
                "error": None,
                "bytes_done": 0,
                "bytes_total": 0,
                "path": None,
            }
        )
    monkeypatch.setattr(updates, "_run_download", lambda _p, _op: None)
    updates.start_download()
    done = threading.Event()

    def second():
        updates.start_download()
        done.set()

    threading.Thread(target=second).start()
    assert done.wait(timeout=2)


def test_engine_chunk_after_cancel_returns_text():
    class Backend:
        def transcribe_chunk(self, pcm, cancelled):
            if cancelled():
                return []
            return [Segment(0, 100, "recognized")]

    app = create_app(backend=Backend(), decode=lambda p: np.zeros(8, np.float32))
    client = TestClient(app)
    assert client.post("/cancel").json()["ok"] is True
    r = client.post("/transcribe_chunk", json={"samples": [0.0, 0.1]})
    assert r.json()["segments"][0]["text"] == "recognized"


def test_cloud_only_batch_uses_remote_not_engine(tmp_path, monkeypatch):
    from slysh.compute import save_engine_mode
    from slysh.providers import save_openrouter

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    save_engine_mode("cloud_only")
    save_openrouter(api_key="sk-test")
    monkeypatch.setenv("GIGAAM_ASR_ID", "openrouter:openai/whisper-1")

    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("c", {"speakers": False, "export": False})
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    job_id = db.create_job(JobKind.FILE, str(wav), batch_id=batch_id)

    remote_calls: list[int] = []
    engine_calls: list[int] = []

    def run_file_job(app, database, jid, source):
        remote_calls.append(jid)
        database.set_status(jid, JobStatus.COMPLETED)

    def ensure_engine(_app):
        engine_calls.append(1)
        raise AssertionError("engine")

    from slysh.batch_runner import start_batch

    app = type("App", (), {"state": type("S", (), {"engine_url": None})()})()
    start_batch(
        app,
        db,
        batch_id,
        run_file_job=run_file_job,
        ensure_engine=ensure_engine,
        run_engine_job=lambda *a: None,
        engine_cancel=lambda _u: None,
    )
    from slysh.batch_runner import get_runner

    runner = get_runner(app)
    if runner.thread:
        runner.thread.join(timeout=5)
    assert remote_calls == [job_id]
    assert engine_calls == []
