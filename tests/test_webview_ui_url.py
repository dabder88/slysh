from __future__ import annotations

from slysh.app import webview_ui_url


def test_webview_ui_url_includes_ui_locale(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    assert webview_ui_url(8765) == "http://127.0.0.1:8765/?ui_locale=ru"


def test_webview_ui_url_ui_locale_en(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    from slysh.ui_locale import save_ui_locale

    save_ui_locale("en")
    assert webview_ui_url(8765) == "http://127.0.0.1:8765/?ui_locale=en"
