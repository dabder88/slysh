"""Wave A3: file batch uses same ASR route as single jobs in cloud_only + remote."""
from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slysh.api import CLOUD_ONLY_ENGINE_MSG, create_ui_app, _run_file_asr_job
from slysh.asr_coordinator import AsrCoordinator
from slysh.catalog import ModelItem
from slysh.db import Database
from slysh.models import JobKind, JobStatus
from slysh.batch_runner import start_batch, get_runner
from slysh import api as api_mod


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)


@pytest.fixture
def remote_model() -> ModelItem:
    return ModelItem(
        id="test-remote",
        label="Remote test",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )


def test_run_file_asr_job_remote_skips_engine_in_cloud_only(
    tmp_path, monkeypatch, remote_model: ModelItem
):
    monkeypatch.setattr(api_mod, "is_cloud_only", lambda: True)
    monkeypatch.setattr(api_mod, "_selected_model", lambda: remote_model)

    def fail_engine(*_args, **_kwargs):
        raise AssertionError("engine must not be started for remote batch job")

    monkeypatch.setattr(api_mod, "_ensure_engine_url", fail_engine)

    completed: list[int] = []

    def fake_remote(_app, db, job_id, _path):
        completed.append(job_id)
        db.set_status(job_id, JobStatus.COMPLETED)

    monkeypatch.setattr(api_mod, "_run_remote_job", fake_remote)

    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    _tiny_wav(wav)
    job_id = db.create_job(JobKind.FILE, str(wav))
    app = create_ui_app(db=db, engine=None)
    db.begin_transcription(job_id)
    _run_file_asr_job(app, db, job_id, str(wav))
    assert completed == [job_id]
    assert db.get_job(job_id)["status"] == JobStatus.COMPLETED.value


def test_batch_start_rejects_cloud_only_without_remote(
    tmp_path, monkeypatch, remote_model: ModelItem
):
    local = ModelItem(
        id="gigaam",
        label="GigaAM",
        backend="gigaam",
        path="",
        ready=True,
        kind="local",
    )
    monkeypatch.setattr(api_mod, "is_cloud_only", lambda: True)
    monkeypatch.setattr(api_mod, "_selected_model", lambda: local)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    batch_id = db.create_batch("T", {})
    wav = tmp_path / "b.wav"
    _tiny_wav(wav)
    db.add_jobs_to_batch(batch_id, [str(wav)])

    resp = client.post(f"/api/batches/{batch_id}/start")
    assert resp.status_code == 400
    assert CLOUD_ONLY_ENGINE_MSG in resp.json()["detail"]


def test_batch_thread_completes_via_remote_runner(
    tmp_path, monkeypatch, remote_model: ModelItem
):
    monkeypatch.setattr(api_mod, "is_cloud_only", lambda: True)
    monkeypatch.setattr(api_mod, "_selected_model", lambda: remote_model)

    def fake_remote(_app, db, job_id, _path):
        db.set_status(job_id, JobStatus.COMPLETED)
        db.set_progress(job_id, 1.0)

    monkeypatch.setattr(api_mod, "_run_remote_job", fake_remote)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    batch_id = db.create_batch("Cloud", {"speakers": True})
    wav = tmp_path / "c.wav"
    _tiny_wav(wav)
    db.add_jobs_to_batch(batch_id, [str(wav)])

    start_batch(
        app,
        db,
        batch_id,
        run_file_job=_run_file_asr_job,
        ensure_engine=api_mod._ensure_engine_url,
        run_engine_job=api_mod._run_engine_job,
        engine_cancel=lambda _url: None,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        runner = get_runner(app)
        with runner.lock:
            active = runner.batch_id is not None
        if not active:
            break
        time.sleep(0.05)
    job = db.list_batch_jobs(batch_id)[0]
    assert job["status"] == JobStatus.COMPLETED.value
