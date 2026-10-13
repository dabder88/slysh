"""Invariant DOM for legacy command bar (#view-legacy) — web/js/legacy.js."""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"

_REQUIRED_IDS = [
    "view-legacy",
    "files-chrome",
    "batches-chrome",
    "btn-add-files",
    "btn-batch-new",
    "btn-batch-add-files",
    "btn-batch-add-folder",
    "batch-target-select",
    "files-hint",
    "batches-hint",
    "legacy-workspace",
    "legacy-files-wrap",
    "legacy-batches-wrap",
]

_REQUIRED_MARKERS = [
    "legacy-command-bar",
    "legacy-toolbar-divider",
    "legacy-hints-wrap",
    "legacy-chrome-actions",
]


def _legacy_section(html: str) -> str:
    m = re.search(
        r'<section id="view-legacy"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-legacy section not found"
    return m.group(0)


def test_legacy_command_bar_dom_ids():
    html = _INDEX.read_text(encoding="utf-8")
    section = _legacy_section(html)
    for elem_id in _REQUIRED_IDS:
        assert f'id="{elem_id}"' in section, f"missing id={elem_id}"
    for marker in _REQUIRED_MARKERS:
        assert marker in section, f"missing {marker}"


def test_batches_chrome_hidden_by_default():
    html = _INDEX.read_text(encoding="utf-8")
    section = _legacy_section(html)
    m = re.search(r'id="batches-chrome"[^>]*', section)
    assert m, "batches-chrome not found"
    assert "hidden" in m.group(0)


def test_transcripts_and_archive_have_no_legacy_tabs():
    html = _INDEX.read_text(encoding="utf-8")
    for view_id in ("view-transcripts", "view-archive"):
        m = re.search(
            rf'<section id="{view_id}"[^>]*>.*?</section>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        assert m, f"{view_id} not found"
        assert "legacy-tabs" not in m.group(0), f"{view_id} must not contain legacy-tabs"
