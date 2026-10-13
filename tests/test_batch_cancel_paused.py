"""Cancel batch when runner is idle but batch status is paused."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import BatchStatus, JobKind, JobStatus


def test_cancel_paused_batch_without_active_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    wav_a.write_bytes(b"x")
    wav_b.write_bytes(b"y")
    j1 = db.create_job(JobKind.FILE, str(wav_a), batch_id=batch_id)
    j2 = db.create_job(JobKind.FILE, str(wav_b), batch_id=batch_id)
    db.begin_transcription(j1)
    db.pause_transcription(j1)
    db.begin_transcription(j2)
    db.pause_transcription(j2)
    db.update_batch(batch_id, status=BatchStatus.PAUSED)

    client = TestClient(create_ui_app(db, engine=None))
    r = client.post(f"/api/batches/{batch_id}/cancel")
    assert r.status_code == 200
    assert (db.get_job(j1) or {})["status"] == JobStatus.CANCELLED.value
    assert (db.get_job(j2) or {})["status"] == JobStatus.CANCELLED.value
    assert (db.get_batch(batch_id) or {})["status"] == BatchStatus.IDLE.value
