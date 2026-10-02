from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.engine_auth import ENGINE_TOKEN_ENV, ENGINE_TOKEN_HEADER
from slysh.engine_server import create_app as create_engine_app
from slysh.providers import save_openrouter


def _loopback_ok_headers() -> dict[str, str]:
    return {
        "Origin": "http://testserver",
        "Referer": "http://testserver/",
    }


def test_loopback_rejects_bad_host(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "1")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.put(
        "/api/compute",
        json={"preference": "cpu"},
        headers={"Host": "evil.example", "Origin": "http://evil.example"},
    )
    assert r.status_code == 403


def test_loopback_rejects_bad_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "1")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.put(
        "/api/compute",
        json={"preference": "cpu"},
        headers={**_loopback_ok_headers(), "Origin": "http://evil.example"},
    )
    assert r.status_code == 403


def test_loopback_rejects_mutating_without_origin_or_referer(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "1")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.put("/api/compute", json={"preference": "cpu"})
    assert r.status_code == 403


def test_loopback_allows_mutating_with_valid_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "1")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.put(
        "/api/compute",
        json={"preference": "cpu"},
        headers=_loopback_ok_headers(),
    )
    assert r.status_code == 200


def test_index_injects_bootstrap_token(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    monkeypatch.setenv("GIGAAM_UI_BOOTSTRAP_HTML", "1")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/")
    assert r.status_code == 200
    assert "__SLYSH_BOOTSTRAP__" in r.text
    assert app.state.ui_bootstrap_token in r.text


def test_locales_public_with_ui_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/locales/ru.json")
    assert r.status_code == 200


def test_ui_session_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    bootstrap = app.state.ui_bootstrap_token
    cookie_name = app.state.ui_cookie_name
    client = TestClient(app, raise_server_exceptions=False)
    denied = client.get("/api/library")
    assert denied.status_code == 401
    session = client.post(
        "/api/ui/session",
        headers={"X-Slysh-Bootstrap": bootstrap},
    )
    assert session.status_code == 200
    assert cookie_name in (session.headers.get("set-cookie") or "")
    ok = client.get("/api/library")
    assert ok.status_code == 200


def test_index_without_html_bootstrap_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_UI_AUTH", "1")
    monkeypatch.setenv("GIGAAM_UI_BOOTSTRAP_HTML", "0")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/")
    assert r.status_code == 200
    assert "__SLYSH_BOOTSTRAP__" not in r.text


def test_engine_requires_token(monkeypatch):
    monkeypatch.setenv(ENGINE_TOKEN_ENV, "secret-token")
    engine = create_engine_app(backend=object(), decode=lambda p: p)
    client = TestClient(engine)
    assert client.get("/health").status_code == 401
    headers = {ENGINE_TOKEN_HEADER: "secret-token"}
    assert client.get("/health", headers=headers).status_code == 200


def test_openapi_disabled_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("SLYSH_DISABLE_OPENAPI", "1")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db, engine=None)
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 404


def test_provider_secret_not_in_settings_json(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    save_openrouter(api_key="sk-test-openrouter-key")
    settings = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-test-openrouter-key" not in settings
    from slysh.providers import openrouter_api_key

    assert openrouter_api_key() == "sk-test-openrouter-key"
