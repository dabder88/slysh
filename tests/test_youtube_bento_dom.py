"""Invariant DOM ids for YouTube bento (#view-youtube) — web/js/youtube.js."""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"

_REQUIRED_IDS = [
    "view-youtube",
    "youtube-lead",
    "youtube-mode-single",
    "youtube-mode-batch",
    "youtube-single-panel",
    "youtube-url",
    "youtube-batch-panel",
    "youtube-batch-mode-lines",
    "youtube-batch-mode-feed",
    "youtube-batch-lines-wrap",
    "youtube-batch-lines",
    "youtube-batch-feed-wrap",
    "youtube-batch-feed-url",
    "youtube-batch-limit",
    "youtube-batch-dateafter",
    "youtube-batch-datebefore",
    "youtube-batch-start-video",
    "youtube-batch-direction",
    "youtube-batch-skip-completed",
    "youtube-batch-export",
    "youtube-batch-export-options",
    "youtube-batch-export-fmt",
    "youtube-batch-export-dirs",
    "youtube-batch-export-dir-add",
    "btn-youtube-batch-resolve",
    "btn-youtube-batch-start",
    "youtube-batch-api-hint",
    "youtube-batch-preview",
    "youtube-batch-status",
    "youtube-method-apify",
    "youtube-method-firefox",
    "youtube-method-cookies",
    "youtube-apify-key",
    "btn-youtube-apify-save",
    "youtube-apify-key-hint",
    "youtube-status-apify",
    "youtube-status-firefox",
    "youtube-status-cookies-file",
    "youtube-status-ytdlp",
    "youtube-status-browser-cookie3",
    "youtube-firefox-meta",
    "youtube-browser-profile",
    "btn-youtube-extract-cookies-quick",
    "btn-youtube-extract-cookies",
    "youtube-import-meta",
    "btn-youtube-import-cookies",
    "youtube-single-actions",
    "btn-youtube-ingest",
    "youtube-ingest-status",
]


def _youtube_section(html: str) -> str:
    m = re.search(
        r'<section id="view-youtube"[^>]*>.*?</section>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert m, "missing #view-youtube section"
    return m.group(0)


def test_youtube_bento_section_has_bento_class():
    html = _INDEX.read_text(encoding="utf-8")
    section = _youtube_section(html)
    assert "youtube-bento-panel" in section


def test_youtube_bento_dom_ids_present():
    html = _INDEX.read_text(encoding="utf-8")
    section = _youtube_section(html)
    missing = [i for i in _REQUIRED_IDS if f'id="{i}"' not in section]
    assert not missing, f"missing ids in #view-youtube: {missing}"


def test_youtube_batch_filters_details_present():
    html = _INDEX.read_text(encoding="utf-8")
    section = _youtube_section(html)
    assert 'class="youtube-batch-filters"' in section
