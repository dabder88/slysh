"""Detect Microsoft Edge WebView2 Runtime on Windows (installer + app)."""

from __future__ import annotations

import glob
import os
import sys

WEBVIEW2_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

_WEBVIEW2_PV_KEY_PATHS = (
    rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}",
    rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}",
    rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\{WEBVIEW2_CLIENT_ID}",
    rf"SOFTWARE\Microsoft\EdgeUpdate\ClientState\{WEBVIEW2_CLIENT_ID}",
)


def _webview2_pv(hive: int, path: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(hive, path) as key:
            version, _ = winreg.QueryValueEx(key, "pv")
    except OSError:
        return None
    text = str(version or "").strip()
    return text or None


def _webview2_pv_from_registry() -> bool:
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in _WEBVIEW2_PV_KEY_PATHS:
            version = _webview2_pv(hive, path)
            if version and version != "0.0.0.0":
                return True
    return False


def _webview2_exe_on_disk() -> bool:
    roots = (
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
    )
    for root in roots:
        pattern = os.path.join(
            root,
            "Microsoft",
            "EdgeWebView",
            "Application",
            "*",
            "msedgewebview2.exe",
        )
        if glob.glob(pattern):
            return True
    return False


def webview2_runtime_installed() -> bool:
    if sys.platform != "win32":
        return True
    return _webview2_pv_from_registry() or _webview2_exe_on_disk()
