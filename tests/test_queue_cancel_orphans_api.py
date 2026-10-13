"""Bulk cancel orphan queue without auto-starting next job."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_cancel_orphans_bulk_cancelled_and_no_pump(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    pumped: list[str] = []
    monkeypatch.setattr(
        api_mod,
        "_pump_asr_queues",
        lambda _app, _db: pumped.append("pump"),
    )

    db = Database(tmp_path / "app.db")
    running_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    queued_a = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"))
    queued_b = db.create_job(JobKind.FILE, str(tmp_path / "c.wav"))
    db.set_status(running_id, JobStatus.RUNNING)
    db.begin_transcription(queued_a)
    db.begin_transcription(queued_b)

    client = TestClient(create_ui_app(db, engine=None))
    r = client.post("/api/queue/cancel-orphans")
    assert r.status_code == 200
    assert r.json().get("cancelled_count") == 3
    for jid in (running_id, queued_a, queued_b):
        assert (db.get_job(jid) or {})["status"] == JobStatus.CANCELLED.value
    assert pumped == []
    assert not db.list_queued_jobs()
