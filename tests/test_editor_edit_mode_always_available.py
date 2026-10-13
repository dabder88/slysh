"""Editor «Правка» tab stays enabled."""
from __future__ import annotations

from pathlib import Path

_EDITOR = Path(__file__).resolve().parents[1] / "web" / "js" / "editor.js"


def test_edit_tab_not_disabled_for_running_file():
    text = _EDITOR.read_text(encoding="utf-8")
    assert "editBtn.disabled = Boolean(runningFile)" not in text
    assert "editBtn.disabled = false" in text


def test_edit_tab_click_not_blocked_by_poll_guard():
    text = _EDITOR.read_text(encoding="utf-8")
    idx = text.index('getElementById("editor-mode-edit")?.addEventListener("click"')
    chunk = text[idx : idx + 280]
    assert "shouldPollEditorJob" not in chunk
