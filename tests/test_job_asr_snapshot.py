from __future__ import annotations

from types import SimpleNamespace

from slysh.db import Database
from slysh.job_asr_snapshot import (
    begin_file_transcription,
    job_uses_remote_asr,
    model_for_job,
)
from slysh.models import JobKind


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
