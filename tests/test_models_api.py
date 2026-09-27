import io
import json
import subprocess

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.compute import load_asr_id
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def _isolate_roots(tmp_path, monkeypatch):
    proj = tmp_path / "proj-models"
    proj.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(proj))
    monkeypatch.delenv("BUZZ_MODEL_ROOT", raising=False)
    monkeypatch.delenv("GIGAAM_MODEL_ROOT", raising=False)
    monkeypatch.delenv("GIGAAM_ASR_ID", raising=False)
    return proj


def _write_gigaam(root):
    folder = root / "gigaam"
    folder.mkdir(parents=True)
    (folder / "e2e.ckpt").write_bytes(b"ckpt")


def _write_whisper(root, size="medium"):
    snap = root / f"models--Systran--faster-whisper-{size}" / "snapshots" / "rev"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    (snap / "model.bin").write_bytes(b"w")
    return snap


def test_models_list_and_put(tmp_path, monkeypatch):
    root = _isolate_roots(tmp_path, monkeypatch)
    _write_gigaam(root)
    snap = _write_whisper(root, "medium")
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    data = client.get("/api/models").json()
    ids = [item["id"] for item in data["items"]]
    assert "gigaam" in ids
    assert "whisper:medium" in ids
    put = client.put("/api/models", json={"id": "whisper:medium"}).json()
    assert put["selected"] == "whisper:medium"
    assert put["source"] == "local"
    assert put["selected_local"] == "whisper:medium"
    assert load_asr_id() == "whisper:medium"
    settings = json.loads((tmp_path / "home" / "settings.json").read_text(encoding="utf-8"))
    assert settings["asr"] == "whisper:medium"
    assert str(snap) == next(i["path"] for i in put["items"] if i["id"] == "whisper:medium")


def test_models_source_local_vs_provider(tmp_path, monkeypatch):
    from slysh.providers import save_openrouter

    root = _isolate_roots(tmp_path, monkeypatch)
    _write_gigaam(root)
    monkeypatch.setattr("slysh.providers.find_gemini_binary", lambda which=None: None)
    save_openrouter(api_key="sk-test")
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    local = client.put("/api/models", json={"id": "gigaam"}).json()
    assert local["source"] == "local"
    remote_id = next(item["id"] for item in local["items"] if item["id"].startswith("openrouter:"))
    put = client.put("/api/models", json={"id": remote_id}).json()
    assert put["source"] == "provider"
    assert put["selected"] == remote_id
    assert put["selected_local"] == "gigaam"
    settings = json.loads((tmp_path / "home" / "settings.json").read_text(encoding="utf-8"))
    assert settings["asr_local"] == "gigaam"
    assert settings["asr_remote"] == remote_id


def test_models_put_unknown_id(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.put("/api/models", json={"id": "whisper:missing"})
    assert r.status_code == 400


def test_models_put_rejects_while_running(tmp_path, monkeypatch):
    root = _isolate_roots(tmp_path, monkeypatch)
    _write_gigaam(root)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    client = TestClient(create_ui_app(db, engine=None))
    r = client.put("/api/models", json={"id": "gigaam"})
    assert r.status_code == 400


def test_status_can_download_local_when_engine_ok(tmp_path, monkeypatch):
    root = _isolate_roots(tmp_path, monkeypatch)
    _write_whisper(root, "tiny")
    monkeypatch.setenv("GIGAAM_ASR_ID", "whisper:tiny")
    monkeypatch.setattr("slysh.api.engine_packages_ok", lambda: True)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    status = client.get("/api/status").json()
    assert status["model"] == "ready"
    assert status["can_download_local"] is True
    assert status["asr_backend"] == "whisper"


def test_spawn_engine_passes_whisper_env(tmp_path, monkeypatch):
    root = _isolate_roots(tmp_path, monkeypatch)
    snap = _write_whisper(root, "small")
    monkeypatch.setenv("GIGAAM_ASR_ID", "whisper:small")
    captured = {}

    class FakeProc:
        def __init__(self):
            self.stdout = io.StringIO("PORT=59999\nmore\n")

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env") or {}
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    app = create_ui_app(Database(tmp_path / "app.db"), engine=None)
    port = api_mod._spawn_engine(app)
    assert port["port"] == 59999
    env = captured["env"]
    assert env["GIGAAM_ASR_BACKEND"] == "whisper"
    assert env["GIGAAM_ASR_ID"] == "whisper:small"
    assert env["GIGAAM_ASR_PATH"] == str(snap)
