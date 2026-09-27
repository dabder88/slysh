import os

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.compute import (
    is_cloud_only,
    load_engine_mode,
    load_preference,
    save_engine_mode,
)
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_engine_mode_defaults_and_cloud_only(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert load_engine_mode() == "auto"
    assert is_cloud_only() is False
    save_engine_mode("cloud_only")
    assert load_engine_mode() == "cloud_only"
    assert is_cloud_only() is True
    save_engine_mode("local")
    assert is_cloud_only() is False


def test_compute_get_and_put_cpu(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GIGAAM_DEVICE", raising=False)
    monkeypatch.delenv("GIGAAM_FORCE_CPU", raising=False)
    monkeypatch.setattr("slysh.compute.cuda_available", lambda: False)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    data = client.get("/api/compute").json()
    assert data["preference"] in ("auto", "gpu", "cpu")
    assert data["effective"] == "cpu"
    assert "cpu" in data["explanations"]

    put = client.put("/api/compute", json={"preference": "cpu"}).json()
    assert put["preference"] == "cpu"
    assert put["effective"] == "cpu"
    assert os.environ.get("GIGAAM_FORCE_CPU") == "1"
    assert load_preference() == "cpu"


def test_compute_put_gpu_warns_without_cuda(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GIGAAM_DEVICE", raising=False)
    monkeypatch.delenv("GIGAAM_FORCE_CPU", raising=False)
    monkeypatch.setattr("slysh.compute.cuda_available", lambda: False)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    put = client.put("/api/compute", json={"preference": "gpu"}).json()
    assert put["preference"] == "gpu"
    assert put["effective"] == "cpu"
    assert put["warning"]


def test_compute_rejects_while_running(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    client = TestClient(create_ui_app(db, engine=None))
    r = client.put("/api/compute", json={"preference": "cpu"})
    assert r.status_code == 400


def test_compute_rejects_bad_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.put("/api/compute", json={"preference": "tpu"})
    assert r.status_code == 400
