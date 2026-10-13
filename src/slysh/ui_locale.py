from __future__ import annotations

import os

from slysh.compute import _read_settings, mutate_settings
from slysh.paths import install_ui_locale_seed_path
UI_LOCALES = frozenset({"ru", "en"})
DEFAULT_UI_LOCALE = "ru"


def normalize_locale_hint(hint: str | None) -> str:
    if not hint:
        return DEFAULT_UI_LOCALE
    token = str(hint).strip().lower().split(",")[0].split("-")[0]
    return "en" if token == "en" else DEFAULT_UI_LOCALE


def load_ui_locale() -> str:
    stored = str(_read_settings().get("ui_locale") or "").strip().lower()
    if stored in UI_LOCALES:
        return stored
    return DEFAULT_UI_LOCALE


def resolve_ui_locale(hint: str | None = None) -> str:
    data = _read_settings()
    stored = str(data.get("ui_locale") or "").strip().lower()
    if stored in UI_LOCALES:
        return stored
    locale = normalize_locale_hint(hint)

    def patch(data: dict) -> None:
        data["ui_locale"] = locale

    mutate_settings(patch)
    return locale


def save_ui_locale(locale: str) -> str:
    value = str(locale).strip().lower()
    if value not in UI_LOCALES:
        raise ValueError("Нужно ru или en")
    def patch(data: dict) -> None:
        data["ui_locale"] = value

    mutate_settings(patch)
    return value


def consume_install_ui_locale_seed() -> str | None:
    """Apply language chosen in Setup.exe on the next launch (incl. upgrade)."""
    path = install_ui_locale_seed_path()
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    locale = "en" if raw == "en" else DEFAULT_UI_LOCALE
    save_ui_locale(locale)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return locale


def webview_language_tag(locale: str | None = None) -> str:
    loc = (locale or load_ui_locale()).lower()
    return "en-US" if loc == "en" else "ru-RU"


def configure_webview_browser_language() -> None:
    """WebView2 native date pickers follow Chromium --lang (set before first WebView2 init)."""
    flag = f"--lang={webview_language_tag()}"
    prev = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    tokens = [t for t in prev.split() if t and not t.startswith("--lang=")]
    tokens.append(flag)
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join(tokens)
