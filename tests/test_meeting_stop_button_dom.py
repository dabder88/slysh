"""Meeting record stop button visibility (parity with dictaphone)."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
_MEETING_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "meeting.js"
_INPUT_CSS = Path(__file__).resolve().parents[1] / "web" / "styles" / "input.css"


def _meeting_section(html: str) -> str:
    m = re.search(
        r'<section id="view-meeting"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-meeting section not found"
    return m.group(0)


def test_meeting_stop_button_has_live_stop_class():
    section = _meeting_section(_INDEX.read_text(encoding="utf-8"))
    assert re.search(
        r'id="btn-meeting-stop"[^>]*class="[^"]*live-stop-btn',
        section,
        re.IGNORECASE,
    )


def test_meeting_js_uses_active_recording_class():
    text = _MEETING_JS.read_text(encoding="utf-8")
    assert "is-active-recording" in text
    assert "btn-meeting-stop" in text


def test_meeting_stop_button_css_in_input():
    css = _INPUT_CSS.read_text(encoding="utf-8")
    assert "meeting-bento-toolbar-card" in css and "live-stop-btn" in css
