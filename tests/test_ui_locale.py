import json
import os

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.compute import settings_path
from slysh.db import Database
from slysh.ui_locale import (
    configure_webview_browser_language,
    consume_install_ui_locale_seed,
    load_ui_locale,
    normalize_locale_hint,
    save_ui_locale,
    webview_language_tag,
)
from slysh.paths import install_root, install_ui_locale_seed_path
from slysh.runtime_setup import FRESH_INSTALL_MARKER


def test_normalize_locale_hint():
    assert normalize_locale_hint("en-US") == "en"
    assert normalize_locale_hint("en") == "en"
    assert normalize_locale_hint("ru-RU") == "ru"
    assert normalize_locale_hint(None) == "ru"


def test_save_and_load_ui_locale(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    assert save_ui_locale("en") == "en"
    assert load_ui_locale() == "en"


def test_get_locale_uses_hint_on_first_visit(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    db = Database(home / "app.db")
    client = TestClient(create_ui_app(db, engine=None))
    r = client.get("/api/locale", params={"hint": "en-US"})
    assert r.status_code == 200
    assert r.json()["ui_locale"] == "en"
    data = json.loads(settings_path().read_text(encoding="utf-8"))
    assert data["ui_locale"] == "en"


def test_webview_language_tag():
    assert webview_language_tag("en") == "en-US"
    assert webview_language_tag("ru") == "ru-RU"


def test_configure_webview_browser_language(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.delenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", raising=False)
    configure_webview_browser_language()
    assert "--lang=ru-RU" in os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    save_ui_locale("en")
    configure_webview_browser_language()
    assert "--lang=en-US" in os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]
    assert os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"].count("--lang=") == 1


def test_put_locale_api(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    db = Database(home / "app.db")
    client = TestClient(create_ui_app(db, engine=None))
    r = client.put("/api/locale", json={"ui_locale": "ru"})
    assert r.status_code == 200
    assert client.get("/api/locale").json()["ui_locale"] == "ru"


def test_consume_install_ui_locale_seed(tmp_path, monkeypatch):
    install = tmp_path / "install"
    install.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    seed = install_ui_locale_seed_path()
    seed.write_text("en\n", encoding="utf-8")
    assert consume_install_ui_locale_seed() == "en"
    assert load_ui_locale() == "en"
    assert not seed.is_file()
    seed.write_text("ru\n", encoding="utf-8")
    assert consume_install_ui_locale_seed() == "ru"
    assert load_ui_locale() == "ru"
    assert not seed.is_file()


def test_consume_seed_overrides_on_fresh_install(tmp_path, monkeypatch):
    install = tmp_path / "install"
    install.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    save_ui_locale("ru")
    (install_root() / FRESH_INSTALL_MARKER).write_text("1", encoding="utf-8")
    seed = install_ui_locale_seed_path()
    seed.write_text("en\n", encoding="utf-8")
    assert consume_install_ui_locale_seed() == "en"
    assert load_ui_locale() == "en"
    assert not seed.is_file()


def test_consume_seed_applies_over_existing_settings(tmp_path, monkeypatch):
    install = tmp_path / "install"
    install.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    save_ui_locale("ru")
    seed = install_ui_locale_seed_path()
    seed.write_text("en\n", encoding="utf-8")
    assert consume_install_ui_locale_seed() == "en"
    assert load_ui_locale() == "en"
    assert not seed.is_file()


def test_consume_seed_applies_on_upgrade_without_fresh_marker(tmp_path, monkeypatch):
    install = tmp_path / "install"
    install.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    save_ui_locale("en")
    assert not (install_root() / FRESH_INSTALL_MARKER).is_file()
    seed = install_ui_locale_seed_path()
    seed.write_text("ru\n", encoding="utf-8")
    assert consume_install_ui_locale_seed() == "ru"
    assert load_ui_locale() == "ru"
    assert not seed.is_file()
