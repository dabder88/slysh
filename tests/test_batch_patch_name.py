from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.batch_rules import normalize_rules
from slysh.db import Database


def test_patch_batch_name_while_running(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    batch_id = db.create_batch("Old", normalize_rules({"batch_type": "youtube"}))
    monkeypatch.setattr("slysh.api.is_batch_active", lambda _app, _bid=None: True)

    response = client.patch(
        f"/api/batches/{batch_id}",
        json={"name": "New name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New name"

    rules_response = client.patch(
        f"/api/batches/{batch_id}",
        json={"rules": normalize_rules({"batch_type": "youtube", "delay_seconds": 10})},
    )
    assert rules_response.status_code == 400
