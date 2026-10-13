"""Bulk pause orphan queue without pumping next job."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment


def test_pause_orphans_bulk_idle_and_no_pump(tmp_path, monkeypatch):
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
    running_id = db.create_job(JobKind.FILE, str(wav))
    queued_a = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"))
    queued_b = db.create_job(JobKind.FILE, str(tmp_path / "c.wav"))
    db.set_status(running_id, JobStatus.RUNNING)
    db.replace_segments(running_id, [Segment(0, 400, "keep")])
    db.begin_transcription(queued_a)
    db.begin_transcription(queued_b)

    client = TestClient(create_ui_app(db, engine=None))
    r = client.post("/api/queue/pause-orphans")
    assert r.status_code == 200
    assert r.json().get("paused_count") == 3
    assert (db.get_job(running_id) or {})["status"] == JobStatus.IDLE.value
    assert (db.get_job(queued_a) or {})["status"] == JobStatus.IDLE.value
    assert (db.get_job(queued_b) or {})["status"] == JobStatus.IDLE.value
    assert db.list_segments(running_id)
    assert pumped == []
