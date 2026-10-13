"""Invariant DOM ids for meeting bento (#view-meeting)."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"

_REQUIRED_IDS = [
    "meeting-save-audio",
    "meeting-recording-actions",
    "meeting-recording-path",
    "btn-meeting-open-recording",
    "btn-meeting-open-recording-folder",
    "btn-meeting-speakers-stop",
]


def _meeting_section(html: str) -> str:
    m = re.search(
        r'<section id="view-meeting"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-meeting section not found"
    return m.group(0)


def test_meeting_save_audio_and_recording_actions_dom():
    html = _INDEX.read_text(encoding="utf-8")
    section = _meeting_section(html)
    for elem_id in _REQUIRED_IDS:
        assert f'id="{elem_id}"' in section, f"missing id={elem_id}"
    assert 'data-i18n="meeting.saveAudio"' in section
