import time

import pytest
from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.compute import save_engine_mode
from slysh.db import Database
from slysh.models import JobKind, Segment


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))


def test_cloud_only_start_local_job_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    save_engine_mode("cloud_only")
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    app = create_ui_app(db=db, engine=None)
    assert app.state.auto_start_engine is False
    client = TestClient(app)
    job_id = client.post("/api/jobs", json={"path": str(wav)}).json()["id"]
    client.post(f"/api/jobs/{job_id}/start")
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("failed", "completed", "cancelled"):
            break
        time.sleep(0.05)
    assert job["status"] == "failed"
    assert "облако" in (job.get("error_text") or "").lower()


def test_cloud_only_remote_job_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    save_engine_mode("cloud_only")

    def fake_transcribe(**kwargs):
        segs = [Segment(0, 500, "облако")]
        on_segments = kwargs.get("on_segments")
        if on_segments:
            on_segments(segs)
        return segs

    monkeypatch.setattr("slysh.api.transcribe_media", fake_transcribe)

    from slysh.catalog import ModelItem

    def fake_selected():
        return ModelItem(
            id="http:groq",
            label="Groq",
            backend="http",
            path="",
            ready=True,
            kind="remote",
        )

    monkeypatch.setattr("slysh.api._selected_model", fake_selected)

    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    client = TestClient(create_ui_app(db=db, engine=None))
    job_id = client.post("/api/jobs", json={"path": str(wav)}).json()["id"]
    client.post(f"/api/jobs/{job_id}/start")
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("failed", "completed"):
            break
        time.sleep(0.05)
    assert job["status"] == "completed"
    assert job["segments"][0]["text"] == "облако"


def test_cloud_only_without_key_does_not_call_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    monkeypatch.setattr(
        "slysh.catalog.find_gemini_binary",
        lambda which=None: "gemini.exe",
    )
    monkeypatch.setattr("slysh.catalog.openrouter_api_key", lambda: "")
    monkeypatch.setattr("slysh.providers.http_api_key", lambda _preset_id: "")
    monkeypatch.setattr("slysh.catalog.list_custom_providers", lambda: [])

    def fail_transcribe(**_kwargs):
        raise AssertionError("transcribe_media must not run without an API key")

    monkeypatch.setattr("slysh.api.transcribe_media", fail_transcribe)
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    chosen = client.post("/api/setup/cloud-only").json()
    assert chosen["needs_provider"] is True
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    job_id = client.post("/api/jobs", json={"path": str(wav)}).json()["id"]
    client.post(f"/api/jobs/{job_id}/start")
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("failed", "completed", "cancelled"):
            break
        time.sleep(0.05)
    assert job["status"] == "failed"
    assert "облако" in (job.get("error_text") or "").lower()
