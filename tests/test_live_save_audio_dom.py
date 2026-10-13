"""Invariant DOM ids for live dictaphone save-audio UI."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"

_REQUIRED_IDS = [
    "live-save-audio",
    "live-recording-actions",
    "live-recording-path",
    "btn-live-open-recording",
    "btn-live-open-recording-folder",
]


def _live_section(html: str) -> str:
    m = re.search(
        r'<section id="view-live"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-live section not found"
    return m.group(0)


def test_live_save_audio_and_recording_actions_dom():
    html = _INDEX.read_text(encoding="utf-8")
    section = _live_section(html)
    for elem_id in _REQUIRED_IDS:
        assert f'id="{elem_id}"' in section, f"missing id={elem_id}"
    assert 'data-i18n="live.saveAudio"' in section
