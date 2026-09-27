from urllib.request import ProxyHandler

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.http_proxy import (
    build_proxy_url,
    load_proxy_config,
    opener_for_remote,
    proxy_target_for_request,
    save_proxy_config,
    should_use_proxy,
)


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "models"))
    (tmp_path / "models").mkdir()
    monkeypatch.setattr("slysh.providers.find_gemini_binary", lambda which=None: None)
    return home


def test_build_proxy_url_encodes_credentials():
    url = build_proxy_url(
        {
            "host": "proxy.example.com",
            "port": 8080,
            "username": "user@x",
            "password": "p:ass",
        }
    )
    assert url.startswith("http://")
    assert "proxy.example.com:8080" in url
    assert "user%40x" in url
    assert "p%3Aass" in url


def test_proxy_target_for_request():
    assert proxy_target_for_request("openrouter", "openrouter:slug") == "openrouter"
    assert proxy_target_for_request("http", "http:groq") == "groq"
    assert proxy_target_for_request("custom", "custom:abc") == "custom"
    assert proxy_target_for_request("cli", "cli:gemini") == "gemini"


def test_should_use_proxy_respects_targets(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_proxy_config(
        enabled=True,
        host="127.0.0.1",
        port=3128,
        targets={"groq": True, "openrouter": False},
    )
    assert should_use_proxy("http", "http:groq")
    assert not should_use_proxy("openrouter", "openrouter:x")


def test_save_validates_enabled_host(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    try:
        save_proxy_config(enabled=True, host="")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "хост" in str(exc).lower()


def test_api_proxy_put_returns_password(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    db = Database(tmp_path / "home" / "app.db")
    client = TestClient(create_ui_app(db, engine=None, auto_start_engine=False))
    resp = client.put(
        "/api/proxy",
        json={
            "enabled": True,
            "host": "proxy.local",
            "port": 8080,
            "username": "u",
            "password": "secret-pass",
            "targets": {"groq": True, "openai": False},
        },
    )
    assert resp.status_code == 200
    proxy = resp.json()
    assert proxy["password_set"]
    assert proxy["password"] == "secret-pass"
    assert proxy["targets"]["openai"] is False
    cfg = load_proxy_config()
    assert cfg["password"] == "secret-pass"


def test_opener_for_remote_uses_proxy_handler(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_proxy_config(
        enabled=True,
        host="10.0.0.1",
        port=8888,
        username="a",
        password="b",
        targets={"groq": True},
    )
    built = []

    def fake_build_opener(handler):
        built.append(handler)
        return type("O", (), {"open": lambda *a, **k: None})()

    monkeypatch.setattr("slysh.http_proxy.build_opener", fake_build_opener)
    opener_for_remote("http", "http:groq")
    assert len(built) == 1
    assert isinstance(built[0], ProxyHandler)
