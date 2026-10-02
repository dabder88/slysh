from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.providers import save_apify


def test_providers_masked_without_session(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    save_apify(api_key="apify-secret-token-xyz")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/api/providers").json()
    apify = data["apify"]
    assert apify["api_key_set"] is True
    assert "api_key_masked" in apify
    assert apify["api_key_masked"].startswith("apif")
    assert apify.get("api_key") == "apify-secret-token-xyz"


def test_providers_blocked_without_ui_session_when_auth_on(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    save_apify(api_key="hidden")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/providers")
    assert r.status_code == 401


def test_providers_reveal_after_ui_session(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    save_apify(api_key="apify-secret-token-xyz")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    bootstrap = app.state.ui_bootstrap_token
    client = TestClient(app, raise_server_exceptions=False)
    session = client.post("/api/ui/session", headers={"X-Slysh-Bootstrap": bootstrap})
    assert session.status_code == 200
    data = client.get("/api/providers").json()
    assert data["apify"].get("api_key") == "apify-secret-token-xyz"


def test_apify_save_omits_key_when_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    save_apify(api_key="keep-me-please")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    client.put("/api/providers/apify", json={})
    from slysh.providers import apify_api_key

    assert apify_api_key() == "keep-me-please"
