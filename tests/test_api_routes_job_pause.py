"""Job pause route is registered (not HTTP 405)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database


def test_job_pause_route_not_method_not_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.post("/api/jobs/99999/pause")
    assert r.status_code != 405


def test_capabilities_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body.get("job_pause") is True
    assert body.get("queue_bulk") is True
