"""Intake follow-up «Сейчас» starts transcription."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus

_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "intake-followup.js"


def test_intake_followup_js_starts_jobs_and_navigates_queue():
    text = _JS.read_text(encoding="utf-8")
    assert "startIntakeTranscription" in text
    assert "/api/jobs/" in text and "/start" in text
    assert "/api/batches/" in text
    assert 'navigate("queue")' in text


def test_orphans_intake_result_exported():
    assert "export function orphansIntakeResult" in _JS.read_text(encoding="utf-8")


@pytest.mark.parametrize("job_count", [1, 3])
def test_post_start_idle_jobs(tmp_path, job_count: int, monkeypatch):
    import slysh.api as api_mod

    monkeypatch.setattr(
        api_mod,
        "_start_asr_job",
        lambda _app, _db, _job_id, _path, **_kwargs: None,
    )
    db = Database(tmp_path / "app.db")
    ids = []
    for i in range(job_count):
        wav = tmp_path / f"f{i}.wav"
        wav.write_bytes(b"RIFF")
        jid = db.create_job(JobKind.FILE, str(wav))
        ids.append(jid)
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    for jid in ids:
        r = client.post(f"/api/jobs/{jid}/start")
        assert r.status_code == 200
        job = client.get(f"/api/jobs/{jid}").json()
        assert job["status"] in (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
