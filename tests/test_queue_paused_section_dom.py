"""Queue paused section and resume actions."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
QUEUE = ROOT / "web" / "js" / "queue.js"


def test_paused_section_in_html():
    html = INDEX.read_text(encoding="utf-8")
    section = re.search(
        r'<section id="view-queue"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert section
    body = section.group(0)
    assert 'id="queue-paused-list"' in body
    assert 'id="btn-queue-resume-all"' in html


def test_queue_js_resume_wiring():
    text = QUEUE.read_text(encoding="utf-8")
    assert "async function resumeJob" in text
    assert "async function resumeAllPaused" in text
    assert "isJobPausedInQueue" in text
    assert "renderPausedJobRow" in text
    assert "queue-paused-list" in text
