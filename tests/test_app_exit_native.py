from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from slysh.app_exit_native import confirm_exit_native


def test_confirm_exit_native_non_windows_returns_false():
    with patch.object(sys, "platform", "linux"):
        assert confirm_exit_native("en") is False


def test_confirm_exit_native_windows_yes(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    import ctypes

    box = MagicMock(return_value=6)
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", box)
    assert confirm_exit_native("en") is True
    assert "close" in box.call_args[0][1].lower()
