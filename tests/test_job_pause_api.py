"""POST /api/jobs/{id}/pause — orphan and batch delegation."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment


def test_pause_running_orphan_sets_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    job_id = db.create_job(JobKind.FILE, str(wav))
    db.set_status(job_id, JobStatus.RUNNING)
    db.replace_segments(job_id, [Segment(0, 500, "hi")])
    app = create_ui_app(db, engine=None)
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/pause")
    assert r.status_code == 200
    assert r.json().get("ok") is True
    job = db.get_job(job_id)
    assert job["status"] == JobStatus.IDLE.value
    assert db.list_segments(job_id)


def test_pause_batch_job_delegates_to_batch_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    job_id = db.create_job(JobKind.FILE, str(wav), batch_id=batch_id)
    db.set_status(job_id, JobStatus.RUNNING)
    app = create_ui_app(db, engine=None)
    called: list[int] = []

    def fake_pause(app_obj, bid: int) -> bool:
        called.append(bid)
        return True

    monkeypatch.setattr("slysh.api.pause_batch", fake_pause)
    monkeypatch.setattr("slysh.api.is_batch_active", lambda _app, bid: bid == batch_id)
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/pause")
    assert r.status_code == 200
    assert r.json().get("batch_pause") is True
    assert called == [batch_id]


def test_pause_running_orphan_does_not_pump(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    pumped: list[str] = []
    monkeypatch.setattr(
        api_mod,
        "_pump_asr_queues",
        lambda _app, _db: pumped.append("pump"),
    )
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    job_id = db.create_job(JobKind.FILE, str(wav))
    db.set_status(job_id, JobStatus.RUNNING)
    client = TestClient(create_ui_app(db, engine=None))
    r = client.post(f"/api/jobs/{job_id}/pause")
    assert r.status_code == 200
    assert pumped == []
