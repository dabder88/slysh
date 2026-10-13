"""Intake/upload modals close only via explicit controls (not backdrop)."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_INTAKE = _ROOT / "web" / "js" / "intake-followup.js"
_LEGACY = _ROOT / "web" / "js" / "legacy.js"
_INDEX = _ROOT / "web" / "index.html"


def test_intake_followup_no_backdrop_close():
    text = _INTAKE.read_text(encoding="utf-8")
    assert "event.target === modal" not in text
    assert "intake-followup-close" in text


def test_upload_target_no_backdrop_close():
    text = _LEGACY.read_text(encoding="utf-8")
    idx = text.index("const uploadTargetModal = ")
    chunk = text[idx : idx + 2000]
    assert "event.target === uploadTargetModal" not in chunk
    assert 'getElementById("upload-target-close")' in chunk


def test_intake_modals_have_close_buttons_in_html():
    html = _INDEX.read_text(encoding="utf-8")
    assert 'id="intake-followup-close"' in html
    assert 'id="upload-target-close"' in html
    assert "modal-card-close" in html.split("intake-followup-close")[0][-200:] or (
        'id="intake-followup-close"' in html and "modal-card-close" in html
    )
    assert 'class="modal-card-close' in html
