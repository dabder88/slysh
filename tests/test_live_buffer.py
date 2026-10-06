import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.chunking import LIVE_CHUNK_SAMPLES, SAMPLE_RATE
from slysh.db import Database
from slysh.live_buffer import LIVE_MAX_PENDING_SAMPLES, LiveBufferOverflowError, LiveSession
from slysh.models import JobKind, JobStatus, Segment


def test_emits_one_chunk_after_live_window_and_flush_tail(tmp_path):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.zeros(LIVE_CHUNK_SAMPLES, np.float32))
    chunks = session.take_ready_chunks()
    assert len(chunks) == 1
    session.push(np.zeros(SAMPLE_RATE * 2, np.float32))
    assert session.take_ready_chunks() == []
    tail = session.flush()
    assert tail is not None
    assert len(tail) == SAMPLE_RATE * 2
    assert (tmp_path / "rec.wav").exists()

def test_push_overflow_preserves_wav_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.live_buffer.LIVE_MAX_PENDING_SAMPLES",
        LIVE_CHUNK_SAMPLES + 100,
    )
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.zeros(LIVE_CHUNK_SAMPLES, np.float32))
    with pytest.raises(LiveBufferOverflowError):
        session.push(np.zeros(200, np.float32))
    assert (tmp_path / "rec.wav").stat().st_size > 0


@pytest.mark.parametrize(
    "n_samples",
    [0, 1, 3200, 8000, 15999, 16000],
)
def test_flush_tail_sample_counts(tmp_path, n_samples):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    if n_samples:
        session.push(np.zeros(n_samples, np.float32))
    tail = session.flush()
    if n_samples <= 0:
        assert tail is None
    else:
        assert tail is not None
        assert len(tail) == n_samples
    assert session.flush() is None


def test_flush_short_tail_not_discarded(tmp_path):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.zeros(SAMPLE_RATE // 2, np.float32))  # 0.5s
    tail = session.flush()
    assert tail is not None
    assert len(tail) == SAMPLE_RATE // 2


def test_flush_twice_does_not_duplicate_tail(tmp_path):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.ones(8000, np.float32))
    first = session.flush()
    second = session.flush()
    assert first is not None
    assert len(first) == 8000
    assert second is None


def test_take_pending_tail_short_remainder(tmp_path):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.zeros(4000, np.float32))
    tail = session.take_pending_tail()
    assert tail is not None
    assert len(tail) == 4000
    assert session.take_pending_tail() is None


def test_take_pending_tail_keeps_wav_open(tmp_path):
    session = LiveSession(wav_path=tmp_path / "rec.wav")
    session.push(np.zeros(SAMPLE_RATE * 2, np.float32))
    tail = session.take_pending_tail()
    assert tail is not None
    assert len(tail) == SAMPLE_RATE * 2
    assert session.take_pending_tail() is None
    assert session.flush() is None


class _FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start(self):
        return None

    def stop(self):
        return None

    def close(self):
        return None


def test_live_start_falls_back_when_16k_unsupported(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(
        api_mod.sd,
        "query_devices",
        lambda index=None: {"default_samplerate": 16000, "name": "Mic", "max_input_channels": 1},
    )
    attempts: list[int] = []

    class _FakeStream:
        def __init__(self, **kwargs):
            rate = int(kwargs.get("samplerate") or 0)
            attempts.append(rate)
            if rate == SAMPLE_RATE:
                raise OSError("Invalid sample rate [PaErrorCode -9997]")

        def start(self):
            return None

        def stop(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/live/start", json={"device_id": 0})
    assert r.status_code == 200
    assert SAMPLE_RATE in attempts
    assert 48000 in attempts
    assert attempts[-1] == 48000
    client.post("/api/live/stop")


def test_live_start_without_engine_creates_wav_and_job(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/live/start", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "live"
    assert Path(body["source_path"]).exists()
    status = client.get("/api/live/status").json()
    assert status["listening"] is True
    assert status["job_id"] == body["id"]
    stopped = client.post("/api/live/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"


def test_list_input_mics_skips_unavailable(monkeypatch):
    devices = [
        {"max_input_channels": 2, "name": "Good Mic"},
        {"max_input_channels": 2, "name": "Disabled Mic"},
        {"max_input_channels": 0, "name": "Output only"},
    ]

    def query_devices(index=None):
        if index is None:
            return devices
        return devices[index]

    monkeypatch.setattr(api_mod.sd, "query_devices", query_devices)
    monkeypatch.setattr(api_mod, "_mic_is_available", lambda i: i == 0)
    assert api_mod._list_input_mics() == [{"id": 0, "name": "Good Mic"}]


def test_live_start_without_mics_returns_400(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [])
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post("/api/live/start", json={})
    assert r.status_code == 400
    assert "Микрофон не найден" in r.json()["detail"]


def test_live_stop_drains_remaining_audio_on_worker(tmp_path, monkeypatch):
    handled: list[tuple[int, int]] = []

    def tracking_handle(app, db, pcm, *, capture_state=None):
        handled.append((threading.get_ident(), int(len(pcm))))

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", tracking_handle)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/live/start", json={})
    assert r.status_code == 200
    worker_ident = app.state.live["thread"].ident
    session = app.state.live["session"]
    session.push(np.zeros(LIVE_CHUNK_SAMPLES, np.float32))
    deadline = time.monotonic() + 2
    while not handled and time.monotonic() < deadline:
        time.sleep(0.02)
    session.push(np.zeros(SAMPLE_RATE * 2, np.float32))
    job_id = r.json()["id"]
    stopped = client.post("/api/live/stop")
    assert stopped.status_code == 200
    finalize_threads = getattr(app.state, "capture_finalize_threads", {})
    fin = finalize_threads.get(job_id)
    if fin is not None:
        fin.join(timeout=5.0)
    deadline = time.monotonic() + 5.0
    status = ""
    while time.monotonic() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json().get("status") or ""
        if status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
            break
        time.sleep(0.02)
    assert status == JobStatus.COMPLETED.value
    lengths = [n for _, n in handled]
    assert LIVE_CHUNK_SAMPLES in lengths
    assert SAMPLE_RATE * 2 in lengths
    assert handled


def test_append_live_segments_does_not_drop_concurrent_writes(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    job_id = db.create_job(JobKind.LIVE, str(tmp_path / "a.wav"))
    n_threads = 4
    n_each = 25

    def worker(tag: int) -> None:
        for i in range(n_each):
            api_mod._append_live_segments(
                app,
                db,
                job_id,
                [Segment(tag * 10000 + i, tag * 10000 + i + 1, f"{tag}-{i}")],
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    segs = db.list_segments(job_id)
    assert len(segs) == n_threads * n_each


def _live_client(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod.sd, "InputStream", _FakeStream)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    return TestClient(app), app


def test_live_pause_resume_and_start_guard(tmp_path, monkeypatch):
    client, app = _live_client(tmp_path, monkeypatch)
    started = client.post("/api/live/start", json={"device_id": 0})
    assert started.status_code == 200
    job_id = started.json()["id"]
    assert app.state.live["session"] is not None
    assert app.state.live["stream"] is not None

    paused = client.post("/api/live/pause")
    assert paused.status_code == 200
    body = paused.json()
    assert body["listening"] is False
    assert body["paused"] is True
    assert body["session_active"] is True
    assert body["job_id"] == job_id
    assert app.state.live["stream"] is None

    again = client.post("/api/live/start", json={})
    assert again.status_code == 400
    assert api_mod.LIVE_ALREADY_HINT in again.json()["detail"]

    resumed = client.post("/api/live/resume")
    assert resumed.status_code == 200
    rbody = resumed.json()
    assert rbody["listening"] is True
    assert rbody["paused"] is False
    assert app.state.live["stream"] is not None

    client.post("/api/live/stop")


def test_live_clear_requires_stop_and_clears_state(tmp_path, monkeypatch):
    client, app = _live_client(tmp_path, monkeypatch)
    started = client.post("/api/live/start", json={})
    assert started.status_code == 200
    job_id = started.json()["id"]

    blocked = client.post("/api/live/clear")
    assert blocked.status_code == 400

    client.post("/api/live/stop")
    cleared = client.post("/api/live/clear")
    assert cleared.status_code == 200
    assert app.state.live.get("job_id") is None

    # Job remains in database
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["id"] == job_id


def test_live_pause_drains_pending_audio(tmp_path, monkeypatch):
    handled: list[int] = []

    def tracking_handle(app, db, pcm):
        handled.append(int(len(pcm)))

    client, _app = _live_client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", tracking_handle)
    client.post("/api/live/start", json={})
    session = _app.state.live["session"]
    session.push(np.zeros(SAMPLE_RATE * 2, np.float32))
    client.post("/api/live/pause")
    assert SAMPLE_RATE * 2 in handled
    client.post("/api/live/stop")


def test_live_stop_after_pause_completes(tmp_path, monkeypatch):
    client, _app = _live_client(tmp_path, monkeypatch)
    client.post("/api/live/start", json={})
    client.post("/api/live/pause")
    stopped = client.post("/api/live/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"


def test_live_pause_resume_cycles_no_duplicate_asr_samples(tmp_path, monkeypatch):
    """B4.3: repeated pause/resume must not double-count or drop transcribed samples."""
    handled: list[int] = []

    def tracking_handle(app, db, pcm, *, capture_state=None):
        handled.append(int(len(pcm)))

    client, app = _live_client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", tracking_handle)
    client.post("/api/live/start", json={})
    session = app.state.live["session"]
    total_pushed = 0
    for _ in range(4):
        n = SAMPLE_RATE // 2
        session.push(np.zeros(n, np.float32))
        total_pushed += n
        client.post("/api/live/pause")
        client.post("/api/live/resume")
    session.push(np.zeros(LIVE_CHUNK_SAMPLES, np.float32))
    total_pushed += LIVE_CHUNK_SAMPLES
    job_id = app.state.live["job_id"]
    client.post("/api/live/stop")
    fin = (getattr(app.state, "capture_finalize_threads", None) or {}).get(int(job_id))
    if fin is not None:
        fin.join(timeout=5.0)
    assert sum(handled) == total_pushed


def test_live_concurrent_pause_and_stop_is_safe(tmp_path, monkeypatch):
    errors: list[Exception] = []

    client, app = _live_client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_handle_live_chunk", lambda *a, **k: None)
    client.post("/api/live/start", json={})
    session = app.state.live["session"]
    session.push(np.zeros(SAMPLE_RATE, np.float32))

    def pause_loop() -> None:
        try:
            for _ in range(8):
                client.post("/api/live/pause")
                client.post("/api/live/resume")
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=pause_loop, daemon=True)
    t.start()
    client.post("/api/live/stop")
    t.join(timeout=5.0)
    assert not errors
