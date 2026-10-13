from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_requests_app_info_with_ui_locale():
    src = (ROOT / "web" / "js" / "shell.js").read_text(encoding="utf-8")
    assert "/api/app/info?ui_locale=" in src
    assert "resolveMarketingUrlsFromApi" in src


def test_marketing_urls_module_exports():
    src = (ROOT / "web" / "js" / "marketing-urls.js").read_text(encoding="utf-8")
    assert "export function marketingUrlsForLocale" in src
    assert "utm_source=soft" in src
