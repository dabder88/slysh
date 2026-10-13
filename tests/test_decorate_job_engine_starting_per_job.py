"""engine_starting in /api/library is per job, not global."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind


def test_library_engine_starting_only_on_starting_job(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    j1 = db.create_job(JobKind.FILE, str(wav))
    j2 = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"))

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    r0 = client.get("/api/library")
    assert r0.status_code == 200
    by_id = {j["id"]: j for j in r0.json()["orphans"]}
    assert by_id[j1]["engine_starting"] is False
    assert by_id[j2]["engine_starting"] is False

    app.state.engine_starting = True
    app.state.engine_starting_job_id = j1

    r1 = client.get("/api/library")
    by_id = {j["id"]: j for j in r1.json()["orphans"]}
    assert by_id[j1]["engine_starting"] is True
    assert by_id[j2]["engine_starting"] is False

    app.state.engine_starting = True
    app.state.engine_starting_job_id = None

    r2 = client.get("/api/library")
    by_id = {j["id"]: j for j in r2.json()["orphans"]}
    assert by_id[j1]["engine_starting"] is False
    assert by_id[j2]["engine_starting"] is False
