"""Legacy transcript click must not seek on editor route."""
from __future__ import annotations

from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "web" / "js" / "legacy.js"


def test_legacy_transcript_click_skips_editor_route():
    text = _LEGACY.read_text(encoding="utf-8")
    idx = text.index('transcriptEl?.addEventListener("click"')
    chunk = text[idx : idx + 220]
    assert 'getRoute() === "editor"' in chunk
