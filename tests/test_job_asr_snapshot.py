from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.catalog import ModelItem
from slysh.db import Database
from slysh.job_asr_snapshot import (
    begin_file_transcription,
    job_uses_remote_asr,
    model_for_job,
)
from slysh.models import JobKind, JobStatus, Segment


def test_model_for_job_prefers_pinned_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_job_asr_snapshot(job_id, "openrouter:whisper", "openrouter")

    groq = SimpleNamespace(id="openrouter:whisper", backend="openrouter")
    local = SimpleNamespace(id="local:gigaam", backend="gigaam")

    monkeypatch.setattr(
        "slysh.job_asr_snapshot.get_model",
        lambda mid: groq if mid == "openrouter:whisper" else local,
    )
    monkeypatch.setattr(
        "slysh.job_asr_snapshot.load_asr_id",
        lambda: "local:gigaam",
    )

    job = db.get_job(job_id) or {}
    assert model_for_job(job).id == "openrouter:whisper"
    assert job_uses_remote_asr(job)


def test_begin_file_transcription_writes_asr_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "c.wav"))
    item = SimpleNamespace(id="openrouter:whisper", backend="openrouter")
    monkeypatch.setattr("slysh.job_asr_snapshot.current_asr_model", lambda: item)
    begin_file_transcription(db, job_id)
    job = db.get_job(job_id) or {}
    assert job["asr_model_id"] == "openrouter:whisper"
    assert job["asr_backend"] == "openrouter"
    assert job["status"] == "queued"


def test_begin_file_transcription_pins_only_on_fresh_start(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"))
    db.set_job_asr_snapshot(job_id, "openrouter:whisper", "openrouter")

    monkeypatch.setattr(
        "slysh.job_asr_snapshot.current_asr_model",
        lambda: SimpleNamespace(id="local:gigaam", backend="gigaam"),
    )

    begin_file_transcription(db, job_id, reset_progress=False)
    job = db.get_job(job_id) or {}
    assert job["asr_model_id"] == "openrouter:whisper"

    begin_file_transcription(db, job_id, reset_progress=True)
    job = db.get_job(job_id) or {}
    assert job["asr_model_id"] == "local:gigaam"


def test_job_start_pins_asr_snapshot_in_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    remote = ModelItem(
        id="openrouter:whisper",
        label="OpenRouter Whisper",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )
    monkeypatch.setattr(api_mod, "_selected_model", lambda: remote)
    monkeypatch.setattr("slysh.job_asr_snapshot.current_asr_model", lambda: remote)
    monkeypatch.setattr(
        api_mod,
        "_start_asr_job",
        lambda _app, _db, _job_id, _path, **_kwargs: None,
    )

    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    job_id = client.post("/api/jobs", json={"path": str(wav)}).json()["id"]
    idle = client.get(f"/api/jobs/{job_id}").json()
    assert not idle.get("asr_model_id")

    started = client.post(f"/api/jobs/{job_id}/start")
    assert started.status_code == 200
    assert started.json()["asr_model_id"] == "openrouter:whisper"
    assert started.json()["asr_backend"] == "openrouter"

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["asr_model_id"] == "openrouter:whisper"
    assert job["asr_backend"] == "openrouter"


def test_job_resume_keeps_pinned_asr_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    remote = ModelItem(
        id="openrouter:whisper",
        label="OpenRouter Whisper",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )
    local = ModelItem(
        id="local:gigaam",
        label="GigaAM",
        backend="gigaam",
        path="",
        ready=True,
        kind="local",
    )
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    db.set_job_asr_snapshot(job_id, "openrouter:whisper", "openrouter")
    db.replace_segments(job_id, [Segment(0, 2000, "partial")])
    db.set_status(job_id, JobStatus.CANCELLED)

    monkeypatch.setattr(api_mod, "_selected_model", lambda: local)
    monkeypatch.setattr("slysh.job_asr_snapshot.current_asr_model", lambda: local)
    monkeypatch.setattr(
        api_mod,
        "_start_asr_job",
        lambda _app, _db, _job_id, _path, **_kwargs: None,
    )

    client = TestClient(create_ui_app(db=db, engine=None))
    resumed = client.post(f"/api/jobs/{job_id}/start")
    assert resumed.status_code == 200
    assert resumed.json()["asr_model_id"] == "openrouter:whisper"
    assert resumed.json()["asr_backend"] == "openrouter"


def test_retranscribe_repins_asr_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    remote = ModelItem(
        id="openrouter:whisper",
        label="OpenRouter Whisper",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )
    local = ModelItem(
        id="local:gigaam",
        label="GigaAM",
        backend="gigaam",
        path="",
        ready=True,
        kind="local",
    )
    monkeypatch.setattr(api_mod, "_selected_model", lambda: local)
    monkeypatch.setattr("slysh.job_asr_snapshot.current_asr_model", lambda: local)
    monkeypatch.setattr(
        api_mod,
        "_start_asr_job",
        lambda _app, _db, _job_id, _path, **_kwargs: None,
    )

    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    db.set_job_asr_snapshot(job_id, "openrouter:whisper", "openrouter")
    db.set_status(job_id, JobStatus.COMPLETED)

    client = TestClient(create_ui_app(db=db, engine=None))
    again = client.post(f"/api/jobs/{job_id}/retranscribe")
    assert again.status_code == 200
    assert again.json()["asr_model_id"] == "local:gigaam"
    assert again.json()["asr_backend"] == "gigaam"
