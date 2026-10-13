"""Meeting transcript topbar layout invariants."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
_CSS = Path(__file__).resolve().parents[1] / "web" / "styles" / "meeting_bento.css"


def _meeting_section(html: str) -> str:
    m = re.search(
        r'<section id="view-meeting"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-meeting section not found"
    return m.group(0)


def test_meeting_transcript_topbar_structure():
    html = _INDEX.read_text(encoding="utf-8")
    section = _meeting_section(html)
    assert "meeting-transcript-topbar" in section
    assert 'id="meeting-transcript-actions"' in section


def test_meeting_bento_topbar_margin_overrides():
    css = _CSS.read_text(encoding="utf-8")
    marker = ".meeting-bento-panel .meeting-transcript-actions .meeting-post-actions"
    assert marker in css
    assert "margin: 0" in css[css.index(marker) : css.index(marker) + 320]
