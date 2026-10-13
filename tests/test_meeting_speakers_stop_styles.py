"""Meeting speakers stop button styled as danger button."""
from __future__ import annotations

from pathlib import Path

_CSS = Path(__file__).resolve().parents[1] / "web" / "styles" / "meeting_bento.css"
_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_meeting_speakers_stop_css():
    css = _CSS.read_text(encoding="utf-8")
    assert ".meeting-speakers-btn.btn-stop" in css
    assert "background" in css.split(".meeting-speakers-btn.btn-stop")[1][:200]


def test_meeting_speakers_stop_html():
    html = _INDEX.read_text(encoding="utf-8")
    assert 'id="btn-meeting-speakers-stop"' in html
    assert "btn-stop" in html.split("btn-meeting-speakers-stop")[1][:120]
