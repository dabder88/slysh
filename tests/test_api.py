from fastapi.testclient import TestClient
from slysh.api import create_ui_app
from slysh.db import Database

def test_list_jobs_empty(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []
