"""POST /api/setup/engine-repair (E.7)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.db import Database


def test_get_setup_includes_engine_slot_needs_resync():
    client = TestClient(create_ui_app(Database(":memory:"), engine=None))
    body = client.get("/api/setup").json()
    assert "engine_slot_needs_resync" in body
    assert "engine_resync_recommended" in body


def test_post_engine_repair_delegates(monkeypatch):
    calls: list[bool] = []

    def fake_repair(*, force: bool = False):
        calls.append(force)
        return {
            "engine_packages": True,
            "installing": False,
            "engine_resync_recommended": False,
            "engine_slot_needs_resync": False,
            "cloud_only": False,
        }

    monkeypatch.setattr(api_mod, "start_engine_repair", fake_repair)
    client = TestClient(create_ui_app(Database(":memory:"), engine=None))
    r = client.post("/api/setup/engine-repair", json={"force": True})
    assert r.status_code == 200
    assert calls == [True]
