"""Invariant DOM ids for export modal bento."""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"

_EXPORT_MODAL_IDS = [
    "export-modal",
    "export-title",
    "export-close",
    "export-batch-hint",
    "export-fmt",
    "export-name-field",
    "export-name",
    "export-dirs-field",
    "export-dirs-list",
    "export-dir-add",
    "export-favorites-toggle",
    "export-favorites-count-badge",
    "export-favorites-container",
    "export-favorites-pick-empty",
    "export-favorites-pick-list",
    "export-confirm",
    "export-cancel",
]

_SETTINGS_FAVORITES_IDS = [
    "settings-export-favorites-spoiler",
    "settings-export-favorites-count",
    "settings-export-favorite-dirs",
    "settings-export-favorite-add",
    "settings-export-favorite-save",
]


def _export_modal_block(html: str) -> str:
    start = html.find('id="export-modal"')
    assert start >= 0, "missing #export-modal"
    sub = html[start:]
    end = sub.find('id="ctx-menu"')
    assert end > 0, "missing ctx-menu after export-modal"
    return sub[:end]


def test_export_modal_bento_ids():
    html = _INDEX.read_text(encoding="utf-8")
    block = _export_modal_block(html)
    assert "export-modal-card" in block
    missing = [i for i in _EXPORT_MODAL_IDS if f'id="{i}"' not in block]
    assert not missing, missing


def test_settings_favorites_bento_ids():
    html = _INDEX.read_text(encoding="utf-8")
    pane = re.search(r'id="settings-pane-system"[^>]*>.*?</div>\s*</div>\s*</div>\s*</div>\s*</div>', html, re.DOTALL)
    assert pane, "missing settings-pane-system"
    section = pane.group(0)
    assert "settings-bento-spoiler" in section
    missing = [i for i in _SETTINGS_FAVORITES_IDS if f'id="{i}"' not in html]
    assert not missing, missing


def test_settings_export_favorites_spoiler_closed_by_default():
    html = _INDEX.read_text(encoding="utf-8")
    m = re.search(
        r'<details[^>]*id="settings-export-favorites-spoiler"[^>]*>',
        html,
    )
    assert m, "missing settings-export-favorites-spoiler details"
    assert " open" not in m.group(0) and not m.group(0).rstrip().endswith("open>")
