"""Queue screen: waiting jobs section."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
_QUEUE_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "queue.js"


def _queue_section(html: str) -> str:
    m = re.search(
        r'<section id="view-queue"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-queue section not found"
    return m.group(0)


def test_queue_waiting_list_dom():
    html = _INDEX.read_text(encoding="utf-8")
    section = _queue_section(html)
    assert 'id="queue-waiting-list"' in section
    assert 'data-i18n="queue.waitingTranscriptions"' in section


def test_queue_js_waiting_orphans_filter():
    text = _QUEUE_JS.read_text(encoding="utf-8")
    assert "waitingOrphans" in text
    assert "isJobWaiting" in text
    assert "queue-waiting-list" in text
