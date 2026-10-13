from __future__ import annotations

import sys


def confirm_exit_native(locale: str) -> bool:
    """Win32 Yes/No when the WebView exit modal cannot be shown (e.g. evaluate_js off UI thread)."""
    if sys.platform != "win32":
        return False
    loc = (locale or "ru").strip().lower()
    if loc == "en":
        title = "Slysh"
        text = "Are you sure you want to close Slysh?"
    else:
        title = "Slysh"
        text = "Вы уверены, что хотите закрыть программу?"
    import ctypes

    MB_YESNO = 0x00000004
    MB_ICONQUESTION = 0x00000020
    MB_SETFOREGROUND = 0x00010000
    IDYES = 6
    result = ctypes.windll.user32.MessageBoxW(
        None,
        text,
        title,
        MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND,
    )
    return int(result) == IDYES
