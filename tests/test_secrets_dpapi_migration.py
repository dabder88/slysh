from __future__ import annotations

import json

from slysh.compute import mutate_settings
from slysh.http_proxy import load_proxy_config, migrate_proxy_secret, public_proxy_config
from slysh.providers import migrate_legacy_provider_secrets, openrouter_api_key
from slysh.secrets_dpapi import get_nested


def test_migrate_openrouter_key_out_of_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    mutate_settings(
        lambda data: data.update(
            {
                "providers": {
                    "openrouter": {"model": "openai/whisper-1", "api_key": "sk-plaintext-test"},
                }
            }
        )
    )
    migrate_legacy_provider_secrets()
    assert openrouter_api_key() == "sk-plaintext-test"
    assert get_nested(("providers", "openrouter", "api_key")) == "sk-plaintext-test"
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    or_block = settings.get("providers", {}).get("openrouter", {})
    assert "api_key" not in or_block
    bak_path = tmp_path / "settings.json.bak"
    assert bak_path.is_file()
    bak = json.loads(bak_path.read_text(encoding="utf-8"))
    assert "api_key" not in (bak.get("providers", {}).get("openrouter", {}) or {})


def test_migrate_proxy_password_out_of_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    mutate_settings(
        lambda data: data.update(
            {
                "proxy": {
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": 8080,
                    "username": "u",
                    "password": "secret-proxy-pwd",
                    "targets": {},
                }
            }
        )
    )
    migrate_proxy_secret()
    assert load_proxy_config()["password"] == "secret-proxy-pwd"
    pub = public_proxy_config()
    assert pub["password_set"] is True
    assert pub["password"] == ""
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "password" not in (settings.get("proxy") or {})
