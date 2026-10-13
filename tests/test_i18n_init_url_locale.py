from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_i18n_init_prefers_ui_locale_query_param():
    src = (ROOT / "web" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert "export function localeFromUrl" in src
    assert "const urlLocale = localeFromUrl()" in src
    assert "if (urlLocale)" in src


def test_app_exit_prompt_returns_boolean():
    src = (ROOT / "web" / "js" / "app-exit.js").read_text(encoding="utf-8")
    assert "return false" in src
    assert "return true" in src
    assert "initAppExit();" in (ROOT / "web" / "js" / "main.js").read_text(encoding="utf-8")
